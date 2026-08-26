# RED TEAM — BL-015 (second pass)

Date: 2026-08-26  
Target: current `## BL-015` in `paper/boundary_ledger.md` (parent-edited) and `paper/next/boundary_ledger.md` item 8.  
Closed (do not re-litigate): four stations formula-forced; B1/S2 empirically unflippable, not `forced_donor_dominated`; do not claim every univariate reproduces the paper; annual range 14.5 vs 14.8 counterexample.

Verdict: item 8 does **not** say「六站都不含记忆信息」. The four-vs-two distinction is present in both ledgers. No wrong CSV numbers. No illegal unfreeze of a frozen primary. Two leftover overclaims remain.

---

## Checks that passed

**Numbers.** Re-read `results/revision/recoverability_type_classification_uncertainty.csv` at `gap_length=30`. The 3-decimal table matches `donor_component` / `memory_component`. Flip thresholds 0.867 / 0.886 match \(D/(1-D)\) (0.867092… / 0.886094…). acf30 0.762 / 0.590 / 0.397 match `table_01.csv`. 02337170 0.868 matches 0.868193….

**Distinction.** Historical prose: four formula-forced; B1/S2 “not identities”; only 02334430 and P3 unforced memory. Consequence: “Four of eight labels are identities… Two more are practically unflippable.” Item 8: “四站” forced; “B1/S2 不是公式强制”. The first-pass 「六站都不含记忆信息」 sentence is gone from both files.

**Freeze.** Q4 forbids unfreeze / `design_freeze_v4` retarget / rewriting BL-006 types. Stored \(D\), \(M\), 0.407, 0.105 °C, −0.380/−0.300 are untouched.

---

## Must-fix leftovers

### 1. Q3 still assigns the whole headline partition to the estimator

`paper/boundary_ledger.md` Q3:

> The additive \(d/4\) rule cannot emit a memory label once \(R^2_{\mathrm{donor}}\ge 0.5\). This is the same class of defect as BL-011 question 3: **the estimator, not the river, produced the headline partition.**

The first sentence is the identity and is correct. The second sentence is not. The paper’s headline partition is two memory vs six donor. Only four of those eight labels are identities. P3 and 02334430 are unforced memory comparisons; B1/S2 are empirical donor comparisons. Q3 as written re-imports the closed “six of eight carry no memory information” claim under a different name.

Fix: keep the identity sentence; replace “headline partition” with “the four \(R^2_{\mathrm{donor}}\ge 0.5\) labels” (or “those four donor labels”).

### 2. Next-paper item 8 says the degeneration has already been replaced

`paper/next/boundary_ledger.md` item 8:

> 下一篇把它当资产：我们自己找到并**替换了**这套退化；…主证据是真实数据上相对邻站 R² 的增量 ΔR²。

「找到」is the ledger asset (the identity). 「替换了」is past tense and treats the operator swap as done. Real-data \(\Delta R^2\) after donor \(R^2\) is Phase 4 and is explicitly missing in BL-015. This is a v9 confirmatory smuggle, not an unfreeze of historical numbers.

Fix: 「将替换」/「要用新算子替换」. Keep 「旧公式只用来展示它会在哪里写错」and 「历史验证结果不重开」. Do not write 主证据是 as if the incremental \(\Delta R^2\) already exists.

No other must-fix. Item 8 does not need a rewrite for「六站都不含记忆信息」— that phrase is not there.

---

## Residuals (not must-fix)

- Table column still headed `forced` with “effectively yes” for B1/S2. Prose immediately denies the identity. Sloppy, already distinguished.
- Update line “eight-station 30-day numbers as a frozen audit of the formula identity” treats all eight rows as identity audits. Four are; four are not. Does not change a number.
- Consequence “realized ACF” is lag-loose; the flip math above uses memory / \(\rho(d/4)\), and the table already says \(\rho\).
- Item 8「这是设计缺陷」sits after the B1/S2 sentence. Attachment is slightly ambiguous; the preceding “四站 / B1/S2 不是公式强制” is enough if Q3 and「替换了」are fixed.
- Q5 “baseline #4 under v9” is a protocol pointer, not a completed experiment.
