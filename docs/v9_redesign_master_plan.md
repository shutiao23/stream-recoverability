# v9 redesign master plan (conversation-durable)

Date: 2026-08-26
Status: active execution plan. Not a result. Not a license to claim confirmation.
Source of truth for this conversation: the WRR-format review + T1–T8 gates + 8-phase plan in the parent query.
This file exists so the long task cannot lose the plan across turns.

## One-sentence contribution (target, not achieved)

Stream-temperature recoverability is a network property that can be predicted from fitting-period covariance before any recovery model is fit; the prediction transfers across continents; and it yields a monitoring decision rule that beats length-only operations.

Regulation is a covariate / mechanism, not the headline.

## Current-state facts (do not overwrite with memory)

- Historical paper freeze remains `configs/design_freeze_v4.yaml`. Do not retarget `DEFAULT_DESIGN_PATH` or the 134k-run historical pipeline.
- Next-paper freeze as of v8 is `configs/recoverability_study_freeze_v1.yaml` + `docs/research_charter_v1.md` + `docs/protocol_change_v7_to_v8.md`.
- Inventory is 12 downloaded / 6 concurrent-enough / sealed catalog-only. First leave-one-river-out did not pass. Sensor policy did not stably beat 15%.
- Operator already exists: `src/stream_recoverability/analysis/conditional_observability.py`. Additive `d/4` is explicitly not that operator.
- Formula degeneration already coded: `heuristic_degeneration.py`. BL-015 must cite the eight-station identity, not invent a new formula.
- `tests/test_reference_runner.py` and `tests/test_formal_registry_builder.py` use the string `design_freeze_v9` as a *dummy mismatch* version. Those tests do not load a yaml file. Creating a real `configs/design_freeze_v9.yaml` does not require changing those strings.
- `scripts/45_validate_research_charter.py` currently hard-requires `recoverability_study_freeze_v1`. v9 must update the validator, not silently break it.
- Jinsha and Chattahoochee are already `historical_seen` in `configs/network_catalog_v1.yaml`. They never become sealed.

## Locked gates (T1–T8)

### T1 Theory (must)
Four propositions with proofs:
1. Monotonicity: \(O_1\subseteq O_2\Rightarrow\Sigma_{G|O_2}\preceq\Sigma_{G|O_1}\).
2. Submodularity of log-det information gain \(\Rightarrow\) greedy \((1-1/e)\) (Krause et al. 2008).
3. Additive \(d/4\) is the special case under donor–boundary orthogonality + exponential ACF; write bias \(\varepsilon_\perp+\varepsilon_{d/4}\) and the degeneration region \(R^2_{\mathrm{donor}}\ge 0.5\).
4. Bonus: any estimator MAE \(\ge\sqrt{2/\pi}\cdot\overline{\mathrm{sd}}(\Sigma_{G|O})\) under a second-order Gaussian model.

### T2 Large-sample primary (must)
- \(\ge 150\) networks, \(\ge 3\) stations and \(\ge 8\) overlapping years each, \(\ge 3\) climate zones, \(\ge 2\) continents.
- Inference unit = river network; cluster bootstrap over rivers; \(n\ge 100\); CIs must be reportable.
- Primary: out-of-network Spearman\((\hat{\mathcal R},\text{achieved skill})\ge 0.60\).
- Two CI rules, both locked: 95% CI lower bound \(> 0.40\), *and* that same lower bound above the four preregistered univariate baseline *point estimates*. Do not drop 0.40 because the six-river pilot missed it.
- Calibration: sealed |predicted−achieved| skill median bias \(< 0.10\), slope \(\in[0.8,1.2]\).

### T3 Decision (must; either a or b)
- (a) Placement: greedy log-det vs strongest non-oracle baseline (random, degree, distance, correlation, Oh & Bartos 2025 QR) worst-case MAE reduction \(\ge 15\%\) in \(\ge 3\) climate zones; report oracle gap.
- (b) Gap triage (preferred headline): at a fixed false-release rate (e.g. 5% of fills with error \(>0.5^\circ\mathrm{C}\)), safe-fill fraction improves \(\ge 30\%\) relative (\(\ge 15\) percentage points absolute) vs length-only.

### T4 Real missing (must)
Reproduce the main conclusion on a natural-outage subset. Inputs already exist: `real_missing_blocks.csv`, `willamette_mainstem_real_missing_blocks.csv`.

### T5 Confound control (must)
Topology-matched regulation effect (donor count/direction, nearest-donor distance, drainage area, climate). Synthetic twin design: dam-like node not at endpoint; endpoint not dam-like.

### T6 Honest boundary (must)
At least one generalizability failure zone with a tested mechanism (preferred: SEPlains reversal × GAGES-II BFI).

### T7 Sealed confirmatory (must)
\(\ge 30\)–\(40\) networks never used for method development; numeric thresholds preregistered; evaluate-once. Reuse once-lock / governance.

### T8 Public data (strongly recommended)
Primary analysis 100% USGS / Hub'Eau / FOEN / UK EA. Jinsha becomes SI regional case.

Accept path: T1–T7. If T3 fails but T1, T2, T4, T5, T7 hold, downgrade title from decision to predictability.

## Four preregistered univariate baselines

1. gap-length only
2. acf only
3. donor \(R^2\) only
4. additive \(d/4\) heuristic (legacy primary, now baseline #4)
Also required as a spatial/topology baseline: nearest-donor distance or correlation.

## Split (network-atomic)

Target fractions: development 50% / validation 20% / sealed 30%.
Sealed \(\ge 40\) networks, of which \(\ge 10\) outside North America.
Forbidden: station-level split; using Jinsha or Chattahoochee as sealed; reading sealed temperatures during development.

v8 freeze used 40/20/40 and inventory 12–20. That is superseded. Do not remap the current 19-network catalog in Phase 0; only lock the *rule*. Catalog expansion is Phase 3.

## Eight phases and this conversation's job

| Phase | Goal | First concrete artifacts |
| --- | --- | --- |
| 0 | Stop-loss + preregister | `docs/protocol_change_v8_to_v9.md`, `configs/design_freeze_v9.yaml`, BL-015, validator/charter update |
| 1 | Operator + theory | `paper/theory.md`, operator extensions, Shapley, synthetic bias tables |
| 2 | Identifiability + twins | `results/framework/synthetic_v2/`, twin design |
| 3 | Corpus | public catalog expansion, sealed lock, quality flags |
| 4 | Main experiment | nested ablation, calibration, cluster bootstrap |
| 5 | Decision + real missing | policy curves, triage ROC, natural outages |
| 6 | Mechanism | matched regulation, BFI, drift rule |
| 7 | Sealed once-open | confirmatory freeze + once-lock |
| 8 | Writing | new title, key points, figure plan |

## Adversarial rule (this conversation)

Every deliverable is produced by two local subagents (no worktrees):
- Blue: implement to the written spec.
- Red: attack completeness, contract breakage, overclaim, and hidden shrinkage of T1–T8.
Parent reviews both and merges. Red files live under `docs/_adversarial/`.

## Failure branches (do not “rescue” by retuning)

- Operator no better than donor \(R^2\): retitle to predictability; do not tune to save T1 novelty.
- Placement wins only single-digit % vs random: headline on triage (b).
- Gaussian second-order fails PIT/QQ: keep monotonicity; switch to quantile-width.
- Qualified networks \(<100\): relax to 3 stations / 6 years and report the relaxation; RGCN as supplementary policy bed.
- Sealed miss: write the miss in the ledger; do not unfreeze.

## What Phase 0 must not do

- Do not open sealed temperatures.
- Do not retarget historical `design_freeze_v4` execution.
- Do not delete `recoverability_study_freeze_v1.yaml`.
- Do not claim formal evidence, headline license, or reservoir causation.
- Do not treat the 12-river pilot numbers as confirmatory.
- Do not invent new eight-station numbers; cite `results/revision/recoverability_type_classification_uncertainty.csv`.

## Phase 0 pass gate

`python scripts/45_validate_research_charter.py` exits 0 against the v9 freeze.
Historical formal-roster tests that pin `design_freeze_v4` still pass.
BL-015 exists in `paper/boundary_ledger.md` and records the \(R^2_{\mathrm{donor}}\ge 0.5\) identity as a design defect, not an empirical discovery.

## Parent review of Phase 0 adversarial pairs (2026-08-26)

Blue wrote the protocol, freeze, charter, validator, and BL-015. Red attacked before some drafts landed. Parent merge decisions:

1. **Keep `configs/design_freeze_v9.yaml` as the next-paper freeze name** (user request). It is not the historical executable. `DEFAULT_DESIGN_PATH` stays v4. Dummy mismatch strings in two tests stay.
2. **Keep Spearman ≥ 0.60 locked in Phase 0** (user request). Treat it as a confirmatory floor. Development may only raise it.
3. **Accept Red on the 0.40 CI floor.** Do not drop the floor the 6-river pilot missed. v9 locks *both* CI rules: lower bound > 0.40 *and* lower bound above the four univariate baseline point estimates.
4. **Accept Red on burned rivers.** Jinsha, Chattahoochee, and the 12 downloaded rivers are never sealed.
5. **Accept Red on Loire / Swiss.** They do not count toward T8 or the ≥10 non-North-America sealed set until daily history is public.
6. **Accept Red on B1/S2.** Four stations are formula-forced. B1/S2 are empirically unflippable, not identities. Do not write “any univariate reproduces the paper.”
7. **One sealed absolute floor: 40.** 30% is the mix target, not a second floor.
8. `evaluate_success` now reads the v9 freeze and reports `thresholds_locked: true`.
9. Rejected Red request to leave numbers unlocked. That would repeat the v8 empty freeze.

Phase 0 is closed only after a second Red pass on the *merged* files.

## Parent review of Phase 1–2 (2026-08-26)

- `paper/theory.md` exists. Red's valid limits were merged: ridged code map is not the population theorem; (1−1/e) is only for log-det F; ε_⊥ includes a two-sided remainder; Prop 4 is Gaussian only.
- Operator `recoverability_r`, Shapley, and bias terms exist and tests pass. Empirical incomplete lags now withhold instead of filling zeros.
- Twin 2×2 landed under `results/framework/synthetic_v2/`. Joint gate **failed honestly**: operator AUC 1.00 and univariate max AUC 1.00, because dam-like was defined as high AR + isolation. Do not retune the generator to manufacture 0.65. Hard-negative (interior dam vs ordinary endpoint) is the scientifically relevant contrast and is also currently tautological on ACF. This is a development result, not confirmation.

## Parent review of Phase 3–4 stop-loss (2026-08-26)

- Honest public-USGS catalog count is **98** (name+HUC2, 3 stations, 8-year *subset* of catalog dates). Still <100 and <<150. Catalog overlap is not post-download concurrency. HUC8-only 166 is exploratory. Loire/Swiss are not counted.
- Phase 4 stop-loss on 5 scored public rivers: station nested ΔR² after donor R² is **+0.162** for the operator and **+0.005** for the old heuristic. Network Spearman operator 0.90 vs donor 0.60. `evaluate_success` failed confirmatory eligibility. Do not sell this as T2. Clearwater dropped by a 50 °C MAE cap; Delaware did not score after the year split.

## Still open (do not mark the goal complete)

## Still open (do not mark the goal complete)

Phase 3 downloads (in progress: USGS v2 79 rivers / 310 sites; Hub'Eau instantaneous spans ≠ daily T8); full Phase 4 grid with 20 placements; T3 decision; T4 real missing scoring (geometry wired, first run 0 gaps, re-run with 7-day floor); T5 matched regulation; T6 BFI/SEPlains; T7 sealed once-open; Phase 8 writing.
