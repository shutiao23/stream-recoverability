# Gate revision log v2 (2026-09-03)

Status: revision of the v14 GO gates G2/G3 after the adversarial review (paper/v14_plan/REVIEW_v14.md, Major 1).  The original `gates.json` and `REPORT.md` were left untouched as the historical record; this file and `gates_v2.json` are the revision trail.

## 1. Original definitions (paper/v14_plan/PLAN.md, section 3.4, frozen before P0)

> - **G1** 收益排序的网络级 Spearman ≥ 0.35,且配对 bootstrap 95% CI 下界 > 0;
> - **G2** 显著优于旧风险曲线:配对 Δρ 的 95% CI 完全在零以上;
> - **G3** top-20% 预算下每缺口平均实现收益 ≥ 全panel 平均的 1.3 倍,且有害处理率 < 15%;
> - **G4** 至少在两个时长(7/30/90/180 中)上 G1 独立成立。

## 2. Reasons for revision (WORKPLAN_v14.md section 1.1)

1. **G3 (cross-duration top-20%) was passed by a one-line rule.**  Across durations the top-20% budget is dominated by gap length: ranking by `duration_only_prediction` selects only 7-day placements, and that one-line rule matches or beats the method.  Composition of the selected units by duration 7/30/90/180 d:

| selection | mean realized benefit | composition 7/30/90/180 d |
|---|---|---|
| diff, archived placement-level (budget_curve.csv, n=3460) | +0.922 C | 38% / 26% / 15% / 10% / 7% / 4% |
| duration-only, archived placement-level | +0.891 C | 85% / 15% / 0% / 0% / 0% / 0% |
| r6_diff, archived placement-level | +0.902 C | 44% / 26% / 14% / 8% / 6% / 3% |
| diff, reviewer-style unit-level top-175 of 874 units | +0.890 C | 44% / 26% / 13% / 8% / 6% / 3% |
| duration-only, reviewer-style unit-level | +0.890 C | 85% / 15% / 0% / 0% / 0% / 0% |
| (all second-panel direct placements) | +0.217 C | 26% / 26% / 25% / 24% |

The reviewer's own composition table (REVIEW_v14.md Major 1; quoted in WORKPLAN_v14.md 1.1) reads: diff +0.899 selecting 66/19/10/4% by duration vs duration-only +0.896 selecting 100/0/0/0%, mean difference 0.003 C - the unit-level recompute above reproduces the 66/19/10/4 shares and +0.878 C exactly, with the duration-only mean moving within tie-break noise (+0.897 here, their draws +0.896..+0.906) because the duration-only predictor is flat inside each duration.  The reported ratio 17.6x (= +0.922 C / +0.217 C) divides by a near-zero denominator; ratios against near-zero denominators must not be reported as effect sizes (WORKPLAN_v14.md section 1.4; differences and absolute values only).
2. **G3's harmful rate was duration-confounded.**  Within-duration top-20% harmful rates are 9.4%/10.9%/25.1%/62.7% for 7/30/90/180 d (diff predictor, recomputed exactly from budget_within_duration.csv); they must be reported per duration, never as a single number.
3. **G2 was a win over a negatively correlated baseline.**  The old risk curve ranks realized benefit at placement level with rho -0.361 (second panel, direct pooled), so the paired delta of +0.908 [0.845, 0.970] arises from beating a baseline worse than random.  G2 is redefined as the paired comparison against r6_diff, the strongest station-history baseline; the old comparison is kept below as a diagnostic.
4. **The aggregation level was wrong for the increment.**  The differential curve's advantage over r6_diff is seasonal and only visible at placement level within duration strata: r6_diff is constant within (station, duration) and cannot rank placements there, while unit-level aggregation erases the increment (see paired_diff_vs_r6_unit_diagnostic.csv).

## 3. New definitions and current verdicts

- **G1** unchanged: network level pass 6/6 (second panel, derived_network_level.csv); placement-level status per duration in the plan's 0.25-0.35 partial-GO band vocabulary.
- **G2 (v2)**: paired network-cluster bootstrap delta of diff over r6_diff, placement level within duration; PASS if CI lower > 0.  Pass 10/12 cells (round-2 grid 7/14/30/60/90/180 d); the first-panel 90 d cell CI crosses zero (reported honestly).  Seed 20260903, 2000 draws; canonical table in paired_diff_vs_r6.csv.
- **G3 (v2)**: within-duration-stratum top-20% budget; margins of diff over duration-only from budget_within_duration.csv (second panel, 7/14/30/60/90/180 d) = 7 d +0.22 / 14 d +0.28 / 30 d +0.23 / 60 d +0.32 / 90 d +0.32 / 180 d +1.01 C; bootstrap (2000 network-cluster draws, uniform random 20% as the duration-only policy per draw) CIs exclude zero in 6/6 strata.
- **G4** unchanged: pass on >= 2 durations (pass_count 6).

## 4. Order-of-events statement (required by WORKPLAN_v14.md section 1.1)

The gate revision was made **after** the adversarial review independently recomputed the duration-only comparators (cross-duration budget composition and within-duration budget rows) and **before** any new experimental data were collected.  No new panel data exist beyond the archived P0 runs; every P0 output used here (placement_predictions_*.csv, unit_predictions_*.csv, differential_fitting_losses_*.csv, budget_within_duration.csv, budget_curve.csv, gates.json, REPORT.md) is the archived run and was not regenerated for this revision.  This is the honest-labeling practice of Pfister & Kirchner (2017, WRR 53(3), 'Debates - Hypothesis testing in hydrology: theory and practice', key pfister2017debates in paper/references.bib): the revision is disclosed, dated, and ordered relative to the evidence it reinterprets.

## 4a. Round-2 extension (2026-09-04): 14/60-d fitted durations

After REVIEW_v14_round2.md (Major 2), 14- and 60-day stratified artificial gaps were cut inside the fitting years of both scored panels with the identical archived machinery (scripts/152_run_v14_r2_fitting_cuts_14_60.py; 4-duration probe reruns reproduce the archived fit losses bit-for-bit, max |dMAE| 8.9e-16).  The differential pipeline (scripts/140-145) was then rerun on the extended six-duration grid (7/14/30/60/90/180 d) and this file, paired_diff_vs_r6.csv, gates_v2.json and budget_within_duration.csv were regenerated from the extended direct-placement sets.  G2'/G3' cell counts above therefore refer to the 12-cell grid (2 panels x 6 durations); the original 8-cell verdicts are superseded by the regenerated tables, and the first-panel 90 d crossing cell remains reported honestly.

## 5. Diagnostics retained from the old gates

- **Old G2 vs the risk curve** (demoted): second panel pooled direct delta +0.908 [0.845, 0.970]; risk placement-level rho -0.361 (negatively correlated with realized benefit - diagnostic only).
- **Old G3 (cross-duration top-20%, 17.6x)** (voided): audit trail in section 2, point 1; full recomputations in gates_v2.json -> diagnostics.old_g3_cross_duration.
- **Harmful rates within top-20% by duration (diff)**: 7 d 9.4% / 14 d 8.4% / 30 d 10.9% / 60 d 14.7% / 90 d 25.1% / 180 d 62.7% (from budget_within_duration.csv; per-duration reporting mandatory).

## 6. Verdict

**GO under redefined gates; 10/12 G2 cells pass and 6/6 G3 margins pass (round-2 grid 7/14/30/60/90/180 d)**

