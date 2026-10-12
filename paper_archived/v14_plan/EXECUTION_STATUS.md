# v14 execution status (2026-09-04, round 3)

Round 1 (2026-09-03): P0–P3 executed, GO; record below is the standing one.
Round 2 (2026-09-04): adversarial review (paper/v14_plan/REVIEW_v14.md) and
6-week workplan executed end-to-end; this file carried the standing record.
Round 3 (2026-09-04): REVIEW_v14_round2.md (Major Revision, three-week plan)
executed: Weeks 1–2 of the plan are done, figures/archive are W3 (remaining
human items below). Every round-1/round-2 verdict still holds unless revised
here.

## Round-3 verdict at a glance

| item | outcome |
|---|---|
| "~60 d" figure withdrawn | No artifact for the "internal sub-grid analysis" exists anywhere under results/; the figure is deleted from every claim surface (skeleton/claims/aux) and replaced by two scale-specific interval thresholds: MAE-scale unit-mean zero crossing 105 d [98–114] (first) / 91 d [85–95] (second) on the fitted 7/14/30/60/90/180/365-d grid (scripts/149, `mae_crossing_ci.csv`), and downstream family-median crossings 39–60 d (Table 6). Johnson m_max = 49 d is reported as falling inside the downstream window and at ~half the MAE crossing — an interval-bracketing statement, never a point convergence |
| −risk comparator | `paired_diff_vs_negrisk.csv` (scripts/150): ρ(−risk)=−ρ(risk); paired diff-over-−risk deltas +0.395/+0.357/+0.344 (first) and +0.478/+0.488/+0.430 (second) at 7/14/30 d, +0.260/+0.302 at 60 d (P(>0)=1.00 all six), decaying at 90 d (0.18) and collapsing at 180 d (first −0.058 [−0.177,+0.020]; second +0.015 [−0.017,+0.049], P=0.82). Manuscript §3.3/§4.2 reframe: irreplaceable range = the positive-benefit regime 7–60 d; 180 d carries harm avoidance only; partial band re-read as the method's strongest cells (§4.7), not an apology |
| Three-family robustness table | `family_benefit_table.csv` (scripts/151): donor_blup_ridge, xgboost_b_d (deployment), seasonal_boundary_ridge on the identical 28,728-placement first-panel geometry vs the climatology default; all three reproduce the sign flip (two strong families between 90–180 d; ridge 60–90 d); reviewer numbers reproduced exactly; §2.8's unexecuted Tier-1/Tier-2 claim rewritten to claim only the tested families (Table 7 in the skeleton) |
| Title/default naming | Title now "…Incremental benefit over calendar-day climatology fill…"; §2.7 norm (v): every benefit statement names its default; aux_text_v14.md created |
| W2-A: 14/60-d fitting cuts | scripts/152: 14- and 60-day stratified artificial-gap cuts in the fitting years of both panels with the archived machinery; 4-duration probe reruns bit-identical (max |dMAE| 8.9e-16) on both panels; extended fit frames `fit_losses_extended_{first,second}.csv` (81,788 / 98,442 rows) with archived rows preserved bit-for-bit (integrity asserts) |
| W2-B: six-duration pipeline | scripts/140/142/143/145/143-p2/144 rerun on the 7/14/30/60/90/180-d grid (station-id string reads fixed so leading-zero USGS ids survive; extended frames input). Paired G2′ re-evaluated: 10/12 cells CI > 0 (all six second-panel cells; crossing cells first-panel 60 d +0.028 [−0.010,+0.068] and 90 d +0.017 [−0.022,+0.056]); G3′ margins 6/6 with P(>0)=1.00; original-grid reviewer cells reproduced (max CI dev 0.004); Table 2 gains 14/60-d rows (unit means +0.848/+0.755 at 14 d; +0.479/+0.320 at 60 d, 5.9%/11.2% harmful-unit share); Table 4 gains 14/60-d budget columns; gates_v2.json + GATE_REVISION_v2.md §4a record the regeneration and its order-of-events |
| Downstream/flip | P4 downstream panels unchanged (five-point grid 7/30/90/180/365); flip analysis (scripts/147) MAE-scale rows extended to the seven-point grid; crossings unchanged (105.3/91.5 d, bracketed 90–180); flip_table.csv now carries 14/60-d MAE reference rows |
| Manuscript/claims | manuscript_v14_skeleton.md fully re-synced to the six-duration grid (Tables 2/3/4/5/7, §2.1/2.3/2.6/3.1–3.5/4.1–4.8/Appendix B, Key Points, abstract, conclusions); claims_v14.md rows C-G2′/C-G3′/C2 targets/C5/C-R2B and diagnostics updated with regeneration markers; aux_text_v14.md mirrored |

## Headline numbers to publish (standing, all artifacts frozen on the six-duration grid)

1. Duration structure of realized benefit over the climatology default (unit
   means; harmful-unit share): first +0.979/+0.848/+0.684/+0.479/+0.260/−0.885/
   −2.502 at 7/14/30/60/90/180/365 d (harmful 0.0/0.0/0.0/5.9/27.4/83.6/94.4%);
   second +0.906/+0.755/+0.553/+0.320/+0.036/−1.500/−3.893 (0.0/0.0/0.4/11.2/
   46.8/95.6/100.0%). MAE-scale crossing 105 d [98–114] first / 91 d [85–95]
   second; downstream metrics flip earlier (family medians 39–60 d). Johnson et
   al. (2021) m_max = 49 d falls inside the downstream window — interval
   bracketing, not point convergence. The old "~60 d" figure is withdrawn.
2. Paired diff-vs-r6 (placement-within-duration, network-cluster bootstrap):
   10 of 12 cells CI > 0 (all six second-panel cells; crossing cells first-60 d
   +0.028 [−0.010,+0.068] and first-90 d +0.017 [−0.022,+0.056]); largest margin
   second-180 d +0.202 [+0.149,+0.265]. Unit-level aggregation erases the
   seasonal increment (11/12 unit-level CIs straddle zero) — SI diagnostic.
3. Sign-flipped legacy predictor (−risk): irreplaceable range of the
   differential curve = 7–60 d (paired deltas 0.26–0.49, P(>0)=1.00); at 180 d
   −risk nearly ties (0.541 vs 0.556 second; first panel the sign flip is if
   anything better). Three-level decomposition (second panel, unit level):
   between-network diff 0.615 vs duration-only 0.400; within-network demeaned
   0.870 vs 0.868; per-network mean 0.843 vs 0.886; within (network × duration)
   cell placement-level mean 0.218/0.227/0.236/0.241/0.274/0.514.
4. Within-duration top-20% budgets (second): diff +1.219/+1.086/+0.840/+0.629/
   +0.380/−0.636 vs duration-only +1.000/+0.809/+0.605/+0.312/+0.056/−1.647
   (margins +0.22/+0.28/+0.24/+0.32/+0.32/+1.01, P(>0)=1.00 all six) and
   r6-diff (+0.066/+0.069/+0.067/+0.026/+0.013/+0.226); harmful rates
   9.4/8.4/10.9/14.7/25.1/62.7% per duration. Value curves below 1 at every ξ at
   7/14/30/180 d and pooled; bounded excursions ≤1.04 at 60/90 d.
5. Risk-curve vs benefit: placement-within-duration ρ(risk) +0.184/+0.172/
   +0.129/−0.024/−0.192/−0.541 (second, 7/14/30/60/90/180 d); pooled direct
   ρ(diff) 0.547 vs duration-only 0.516 (duration-confounded, Appendix B).
6. Model-family robustness (first panel, Table 7): deployment xgboost_b_d,
   donor_station ridge, seasonal_boundary_ridge all reproduce the sign flip on
   identical placements (deployment and donor ridge flip 90–180 d, ridge
   60–90 d).

## Remaining human-execution items (no compute needed)

Closed by Round 5: Table 1 comparator cells (0 "?" cells remain — the
round-2 fill stands), the abstract trim (249 words) and Key Points
(≤ 140 chars each), and the reference check (all 26 cited keys resolve in
`paper/references.bib`; johnson2021datagap and richardson2007longgaps
positioned as intended). The standing human items are the five W4 steps at
the end of the Round 5 record below (Zenodo DOI, OSF registration, visual
figure QC, HESS Technical Note submission, round-3 response letter).

## Round 4 (2026-09-05, WORKPLAN_v15.md W1: the mechanism rewrite — no new compute)

| item | outcome |
|---|---|
| scripts/152 mechanism/oracle package | `results/v14/p5_mechanism/`: benefit_decomposition.csv (clim MAE flat, −4% / −0.4% over 7→365 d; model MAE ×9.8/×9.0), station_crossings(_summary).csv (ρ = +0.411 second / +0.243 first; quartile medians 75→82→96→98 d / 92→98→101→108 d), regime_structure.csv (inverted U, peak 90 d: +0.179/+0.143), budget_brackets.csv (B ∈ {5,10,20,30,50}% with oracle/random brackets; capture 20–48%; oracle top-20% at 180 d +0.707/+0.382 °C) |
| §3.1 rewritten | Now "The structure of benefit": decomposition law (Table 2a) → station-level prediction → duration structure (Table 2) → two scale-specific thresholds → cross-family "same threshold line, different model curves" (Table 7) → downstream corroboration → Johnson interval bracketing → oracle reconciliation ("do not reconstruct indiscriminately, not do not reconstruct") |
| §3.3 design principle | Opening paragraph + Table 3a (inverted-U prediction, confirmed in both panels); the three boundary conditions reported proactively as the mechanism's confirmations (default-difficulty decision parity at 7 d 0.231 vs 0.221; −risk tie at 180 d 0.541 vs 0.556 / 0.373 vs 0.308; 20–48% capture ceiling) |
| §4.7 apology removed | Partial band re-read as the mechanism's prediction (clim term carries the short-gap information; any reasonable predictor approaches the same ceiling); benchmark-bracket reframing kept with the oracle–random span quantified |
| §4.1 Johnson interval-to-interval | Three scales stated (downstream 39–60 d; MAE 91–105 d; mechanism ≈91 d second); m_max = 49 d inside the downstream window; no single-number coincidence claimed |
| Conclusions item (1) | Mechanism statement with numbers in brackets; rule phrased "do not reconstruct indiscriminately beyond the crossing — select within it" |
| claims_v14.md | Rows C-M1 (law), C-M2 (station prediction), C-M3 (regime structure + boundary conditions) added 2026-09-05 |
| New Fig 1 | `scripts/154_run_v15_fig1_mechanism.py` → `results/v14/p5_mechanism/fig01_mechanism.png` (2×2: law with crossing + shading; three families on one threshold line; station scatters ρ = +0.41/+0.24); final six-figure set assembled in Round 5 (`results/v15/figures/`) |

## Round 5 (2026-09-05, WORKPLAN_v15.md W2+W3+W4 — the two re-runs, figures/format, and the submission package)

**W2.1 — decision endpoint completed (scripts/155, `results/v15/budget_full/`).**
Full Tier-0 suite (diff, risk, neg_risk, duration, r6_diff, default_difficulty,
rh_error, rh_benefit, amplitude, sd, global) at B ∈ {5, 10, 20, 30, 50}% ×
{7, 14, 30, 60, 90, 180} d × both panels, with oracle/random brackets and
capture rates; 95% network-cluster bootstrap CIs (2,000 draws, seed 20260903,
provider-stratified on the second panel) for the oracle and the six main
predictors at every cell. B = 0.20 reproduces the P1 table exactly
(120/120 rows, max |Δ| < 1e−9). Table 4 now carries default_difficulty
(+1.233/+1.074/+0.795/+0.518/+0.237/−1.399 °C, exceeding diff at 7 d — the
mechanism's predicted short-end parity), neg_risk, oracle and random rows;
§3.4 states the sweep, the brackets, and the 20–48% capture ceiling.

**W2.2 — station-level robustness (scripts/156, `results/v15/station_robustness/`).**
Exclusions are exclusively the never-crosses-by-365-d class (31 first / 14
second; no starts-negative, no re-crossings — the 152 filter is exact);
second-panel provider stratification is positive in all three providers
(0.342/0.430/0.365, p ≤ 0.007) — not a single-provider artifact (first panel
mixed, reported honestly); rank-based partial ρ controlling amplitude + sd is
+0.365/+0.563, at or above the zero-order estimate on the same subsets — not
confounded. §3.1 station paragraph and claim row C-M2 updated.

**W3 — figures and format.** Figure set assembled in `results/v15/figures/`
(scripts/157; Fig 1 mechanism from scripts/154): Fig 2 duration structure +
families, Fig 3 regime structure (inverted U + signal migration), Fig 4 main
ranking, Fig 5 decision layer (Table 4 rows + budget sweeps with cluster CIs
at 90/180 d + EC(ξ)/δ), Fig 6 boundaries (decomposition + drift null +
support tiers); round-3 estimator-contrast and downstream-flip figures move
to SI. Abstract rewritten to 249 words (≤ 250) with the mechanism in the
first paragraph; the four Key Points rewritten to ≤ 140 characters each
(137/118/121/126); title now ends "Incremental benefit relative to
climatology fill"; Table 1 verified fully filled (0 "?" cells — the
round-2 fill stands); all 26 citation keys resolve in references.bib
(johnson2021datagap and richardson2007longgaps positioned as intended).

**W4 — submission package.** Software Zenodo record exists (.zenodo.json,
version 1.1.0); the paper-artifact Zenodo deposit + DOI minting and the OSF
registration of protocol v5 are author-credential steps with exact
instructions in osf_registration_package.md (blocking: DOI). Negative-result
note marked submission-ready pending its 3 figures + DOI, with the v15
mechanism anchor sentence added to its implication section. Length checks
pass: abstract 249 w, Key Points ≤ 140 chars each.

### W4 remaining human steps (only these block submission)

1. Zenodo: create the paper-artifact deposit (results/v15 + v14 tables +
   scripts 140–157 + protocol v5) and insert the minted DOI into the
   manuscript, CITATION.cff, and .zenodo.json.
2. OSF: register protocol v5 pre-outcome and record the registration DOI
   (protocol_v5.md §6 wording is frozen; do not edit).
3. Human visual QC of `results/v15/figures/` (all programmatic audits and
   annotation asserts pass).
4. Submit the negative-result note to HESS Technical Note after figures +
   DOI; cite it in the v14 reference list once accepted.
5. Compose the response letter to REVIEW_v14_round3.md (mechanism rewrite,
   three adverse evidence now confirmations, capture ceiling reported, oracle
   reconciled, Johnson interval-to-interval, ~60 d withdrawn).

## Script index (rounds 1–3)

scripts/140_run_p0_differential_stress.py (P0, six-duration grid),
141_run_p3_network_drift.py (P3 covariates), 142_p0_derived_metrics.py,
143_run_p1_benefit_baselines.py, 143_run_v14_p2_decision.py,
144_run_p3_strata_comparison.py, 145_run_paired_diff_vs_r6.py (round-2/3
paired freeze + gates), 145_run_p4_downstream.py (first panel),
145_run_v14_figures.py (v1 figure set), 146_run_p4_downstream_second.py,
147_run_p4_flip_analysis.py (seven-point MAE grid), 148_run_v14_figures_v2.py
(round-2 figure set), 149_run_v14_r2_mae_crossing_ci.py (round-2 threshold
CIs), 150_run_v14_r2_negated_risk.py (round-2 −risk comparator),
151_run_v14_r2_family_table.py (round-2 three-family table),
152_run_v14_r2_fitting_cuts_14_60.py (round-2 14/60-d fitting cuts),
152_run_mechanism_and_oracle.py (v15/W1 benefit law, station crossings, regime
structure, budget brackets with oracle/random),
153_run_v14_figures_r3.py (round-3 figure set),
154_run_v15_fig1_mechanism.py (v15/W1 mechanism Fig 1),
155_run_v15_budget_full.py (v15/W2.1 full budget sweep + cluster CIs),
156_run_v15_station_robustness.py (v15/W2.2 station robustness),
157_run_v15_figures_w3.py (v15/W3 assembled figure set Fig 2–6).
