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

1. Zenodo deposit + DOI minting (WRR hard gate; assemble per
   osf_registration_package.md file tree; DATA_RIGHTS scheme from v13).
2. OSF registration execution (protocol v5; must precede any v5 panel
   scoring; AGU/NO Registered Report wording rules in the package).
3. Visual QC of the regenerated figure set (round-3; figures are re-rendered
   from the six-duration CSVs under scripts/148; programmatic audits +
   annotation assertions pass in-script).
4. W2-C: Table 1 comparator cells (Husic/El Ouahabi/Auer columns, 15 cells)
   filled from the source PDFs (open-access HESS/EGU full texts; the
   Pechlivanidis column is filled); unresolved cells stay "?" with the paper
   cited in the table note.
5. aux_text_v14.md final abstract trim; length check (WRR limits).
6. References re-generation; confirm johnson2021datagap cited (yes, §3.1/§4.1)
   and richardson2007longgaps positioned as prior art + comparator.

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
152_run_v14_r2_fitting_cuts_14_60.py (round-2 14/60-d fitting cuts).
