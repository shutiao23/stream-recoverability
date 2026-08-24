# Boundary ledger

## BL-001 — Proposed/deep model roster

**Observed.** Required seeds for BRITS, CSDI, and the proposed model selected before epoch 50 or otherwise failed the frozen stability path. Proposed lost 27 of 36 difficult validation cells to donor regression.

**Update.** No deep model enters the formal roster. All rankings and architectures move to SI. Excluded runs cannot support a model-class conclusion.

## BL-002 — Universal analytic ceiling

**Observed.** The frozen curve tracks internal best-envelope shape, but 20 of 45 point estimates and nine lower confidence bounds exceed it. Every lower-bound exceedance is at thermally nonstationary P3; B1/S2 have none.

**State controls.** A post-hoc 2016--2020 calibration/denominator reduces lower-bound exceedances to one and reverses 365-day P3 XGBoost skill from 0.209 to -0.588. Annual demeaning retains 0.164 skill.

**Update.** Withdraw the universal information-ceiling claim. Retain a conditional state-specific shape heuristic. Do not claim that three stations prove a stationary ceiling.

## BL-003 — Frontier-path divergence

**Observed.** `statistical_frontiers.csv` and `dual_frontier_comparison.csv` used different resampling paths and disagreed on identical climatology cells.

**Correction.** Both denominators now use the canonical overlap-aware anchor/year path. All 27 climatology frontier/censoring cells match exactly. See `docs/protocol_change_v5_to_v6.md`.

## BL-004 — Degenerate climatology p-values

**Observed.** All anchors at one station were collapsed to one connected overlap component, so a Wilcoxon test with $n=1$ returned $p=1$ in every row.

**Correction.** Use one cross-gap mean per anchor/year after seed collapse. There are 24 actual finite tests and three explicit reference rows. Fourteen pass BH; seven are positive and seven negative.

## BL-005 — Model-damage node importance

**Observed.** The old same-model estimator produced B1/S2 donor-regression impacts of 2.42/1.98 °C because impaired models performed far worse than climatology.

**Correction.** Reselect the best method after failure and include climatology as a cap. Mean S2→B1 and B1→S2 costs are 0.132 and 0.070 °C. Negative impacts remain visible.

## BL-006 — External confirmation

**Frozen prediction.** Site 02334430 was the only memory-dominated site; the other four were donor-dominated. Full predicted curves were written before confirmation.

**Observed once.** All 540 run units completed. Site 02334430 has the largest 30-to-180-day decline and lowest 180-day skill. All four donor sites retain higher 180-day skill. Absolute prediction errors remain basin/site dependent.

**Update.** Claim qualitative external type confirmation, not universal skill magnitude or five independent-basin replication. No retroactive numeric threshold is called preregistered.

## BL-007 — Submission compliance

**Open.** Restricted Jinsha bytes remain in the development repository history, and no archival software DOI exists.

**Boundary.** The manuscript is scientifically revised but must not be submitted until a coordinated code-only history/release and real archival DOI exist. Reviewer access to restricted data is through AGU GEMS confidential files.
