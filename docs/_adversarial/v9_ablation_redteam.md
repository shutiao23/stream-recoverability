# RED TEAM: Phase 4 stop-loss ablation

Date: 2026-08-26  
Role: attack the Phase 4 nested / stop-loss ablation only. Not a protocol. Not a license to implement.  
Required artifacts: `public_river_operator_ablation*` (any path). **None exist.**  
Read: `results/framework/baseline_nested_r2.csv`, `baseline_predictions.csv`, `baseline_residual_gain.csv`, `results/framework/public_rivers/leave_one_year_scores.csv`, `leave_one_river_out.csv`, `leave_one_river_out_without_clearwater.csv`, `public_river_check.json`, `overlap.csv`, `paper/next/results.md`, `paper/next/manuscript_skeleton.md`, `paper/next/claim_matrix.md`, freeze T2 / incremental / never-sealed, `recoverability_baselines.py`, `real_river_checks.py`, `scripts/47`.

Sealed temperatures were not opened. That is the only check that passes.

---

## Verdict

Phase 4 did not land. There is no real-river operator ablation, no out-of-network nested \(\Delta R^2\) after donor \(R^2\), no calibration table, no cluster bootstrap at \(n\ge 100\).

What exists is the old synthetic identity table (`baseline_nested_r2.csv` last row \(R^2=1.0\)) and the burned-river year-split scores. Those scores were then **subset after seeing the outcome**: Clearwater was scored, produced MAE \(6.6\times 10^4\,^\circ\mathrm{C}\), and was dropped. The surviving \(n=6\) Spearman \(\approx 0.77\) (MAE) is written as the leave-one-river number. That is not T2. It is not a stop-loss. It is the failed 12-river pilot with one river removed by hand.

If Blue treats any of those files as the Phase 4 ablation, T1 novelty and T2 confirmation are both still for sale on a tautology and a peek.

---

## Missing files

No path matches `*public_river_operator_ablation*`. No new nested table under `results/framework/`. `baseline_nested_r2.csv` is still the synthetic suite from `scripts/44` / `run_baseline_suite`. BL-015 already said a real-data nested ablation versus donor-\(R^2\)-only was never reported. It still has not been.

Attack the **required** method, and the files that would be substituted for it.

Required method (freeze + charter + master plan Phase 4):

- Estimand: fitting-period \(\mathcal R\) (Schur; not MAE `predicted_skill`) versus **held-out** achieved skill \(1-E[L(Y_G,f_S)]/E[L(Y_G,f_0)]\), \(f_S\) and climatology fixed on fitting years only.
- Incremental: nested \(\Delta R^2\) after gap-length, ACF, donor \(R^2\), additive \(d/4\). Stop-loss: if the operator adds nothing over donor \(R^2\), retitle to predictability; do not retune.
- Inference unit = river. Out-of-network or cluster-bootstrap over rivers. CIs only at \(n\ge 100\). Do not report a network-level interval from the 12-river pilot.
- Exclusion rules declared on **inputs** before scores. Clearwater is a burned lock river, not a free discard.
- Sealed temperatures stay closed. Phase 4 is development / stop-loss on burned rivers. T7 is later.

---

## 1. Achieved skill is still `predicted_skill` (\(X=Y\))

`predictor_frame` (`recoverability_baselines.py`):

```text
observed = recoverability(mae_S, mae_0)          # 1 - mae_S/mae_0
conditional_covariance = predicted_skill         # 1 - mae_S/mae_0
```

`recoverability()` is the same ratio as `conditional_summaries["predicted_skill"]`. On `baseline_predictions.csv` (28 rows, 7 synthetic rivers × 4 gaps):

```text
max |observed_structural_skill - conditional_covariance| = 0.0
```

`baseline_nested_r2.csv` is therefore an in-sample OLS of \(Y\) on \(\{X_1,\ldots,X_4,Y\}\):

| added | r2 | delta_r2 |
| --- | ---: | ---: |
| gap_length_only | 0.050 | 0.050 |
| acf_only | 0.153 | 0.104 |
| donor_r2_only | 0.909 | 0.756 |
| additive_heuristic | 0.964 | 0.056 |
| **conditional_covariance** | **1.0** | **0.036** |

`baseline_residual_gain.csv`: `r2_with_operator=1.0`, `residual_r2=0.091`. The test `test_operator_explains_residual_after_simple_baselines` still asserts `residual_r2 > 0` on this identity.

This is not a stop-loss. A last-step \(\Delta R^2>0\) is guaranteed once \(X=Y\). Donor \(R^2\) already takes 0.756 of the 0.909; the operator “wins” the residual because it **is** the residual.

`leave_one_year_scores.csv` is not this tautology: `predicted_skill` (train Schur MAE-ratio) ≠ `observed_skill_vs_climatology` (test donor-MAE vs train mean). That file also does not contain `recoverability_r`, donor \(R^2\), ACF, gap-length, or a nested \(\Delta R^2\). It cannot stand in for Phase 4.

**Required method.** \(Y\) = held-out achieved skill. \(X_{\mathrm{op}}\) = fitting-period \(\mathcal R\) (or a calibration of it), not `predicted_skill` computed from the same \(\Sigma_{G|O}\) used to define \(Y\). If the last nested row is 1.0, the table is invalid.

---

## 2. Clearwater was dropped after peeking

`overlap.csv` already had a predeclared input rule: `complete_enough` = overlap years \(\ge 8\) **and** concurrent-four-station days \(\ge 1825\). Clearwater fails by **one day** (1824). Suwannee fails both (5.05 yr, 1648 days).

`scripts/47` does **not** use that rule to score. It scores if `days_with_min_stations >= 365*4` (1460) and `n_stations >= 3`. Clearwater (1824) and Suwannee (1648) both enter `leave_one_year_scores.csv`. Yellowstone (1350) and Rio Grande (1425) do not.

Seven rivers then have finite scores. Clearwater test MAE is 66332 / 8188 / 9701 / 10811 °C; skill \(-10033\) / \(-2607\) / \(-2863\) / \(-0.05\). `paper/next/results.md` and `manuscript_skeleton.md` say, after that number: 数据坏了 / 误差大到不合理，丢掉. Remaining \(n=6\), Spearman \(\approx 0.77\).

That exclusion is not in the freeze, not in `overlap_report`, not in `score_rivers`, and not in any QC constant. There is no predeclared “drop if MAE \(> X\)” or “drop if skill \(< 0\)”.

Suwannee is also `complete_enough=False` and was **kept**, because its MAE looks ordinary (0.17–0.70). Selection is on the realized loss, not on the input rule that would have dropped both rivers before anyone looked at °C.

Orphan file: `leave_one_river_out_without_clearwater.csv`. **No script writes it** (repo-wide grep is empty). Slopes with Clearwater in the training set are \(3.1\times 10^4\)–\(4.8\times 10^4\); holding Clearwater out drops the slope to 1.91; the orphan file is all \(\approx 1.85\)–\(2.07\). Someone reran LORO after the peek.

`public_river_check.json` still includes Clearwater: \(n=7\), Spearman 0.821, CI \((0.094, 1.0)\), `thresholds_locked: false`. Protocol v8→v9 already forbids citing 0.821/0.094 and names 0.77 as the post-drop failed pilot. The 0.77 is therefore the **peeked** number, not a second experiment.

Recomputed on `leave_one_year_scores.csv` (network means):

| set | Spearman(pred MAE, obs MAE) | Spearman(pred skill, obs skill) |
| --- | ---: | ---: |
| 7 rivers (incl. Clearwater) | 0.821 | 0.857 |
| 6 rivers (Clearwater out) | **0.771** | 0.943 |

The published 0.77 is the MAE Spearman after the drop. The T2 estimand is Spearman\((\hat{\mathcal R},\text{achieved skill})\). On the same six rivers that skill Spearman is 0.94. Neither number is T2. Both are available only after seeing Clearwater explode.

**Required method.** Freeze the analysis set on input flags (`complete_enough`, withheld lags, \(n_{\mathrm{eff}}\), physical range) **before** scores. Tombstone the orphan LORO file. If Clearwater is ineligible, it was ineligible at 1824 days, together with Suwannee. You do not get to keep the quiet failure and drop the loud one.

---

## 3. \(n=6\) is being used as T2

T2 (locked): \(\ge 150\) networks (design), inference \(n\ge 100\), out-of-network Spearman\((\hat{\mathcal R},\text{achieved skill})\ge 0.60\), CI lower \(>0.40\) **and** above the four univariate point estimates, sealed calibration later. Freeze interval rule: do **not** report a network-level interval from the 12-river pilot. `six_river_pilot_is_failed_context_not_evidence: true`.

What was written:

- `paper/next/results.md`: 6-river rank correlation \(\approx 0.77\); bootstrap interval \(\approx(-0.01, 1.0)\); lower bound misses 0.40; “没有过关”.
- `paper/next/claim_matrix.md`: row「能预估没见过的真河」= 「6 条河相关大约 0.77」.
- `manuscript_skeleton.md` §5: same 0.77 / 0.40 miss.

Calling it a failed pilot does not make \(n=6\) into T2. Reporting the CI already violates the freeze. `evaluate_success` now sets `confirmatory_eligible` only at \(n\ge 100\), but `network_bootstrap_spearman` still emits a “tested” CI at \(n\ge 5\). The on-disk check file used the 5-river floor.

The six rivers are not even the six `complete_enough` rivers. Concurrent-enough: Delaware, Willamette, Madison, Mahoning, Roanoke, Santa Fe. Scored-after-peek: Willamette, Suwannee, Madison, Mahoning, Roanoke, Santa Fe. Delaware (`complete_enough=True`, 8857 concurrent days) is `could_not_score_any_station`. Suwannee (`complete_enough=False`) is in the T2-shaped table. The “6” that matches the catalog sentence and the “6” that produce 0.77 are different sets.

**Required method.** Phase 4 stop-loss may quote a development Spearman on the predeclared burned set. It may not write a network CI. It may not lock `incremental_over` or T2 floors from six points. T2 starts at \(n\ge 100\) or the freeze’s written relaxation (3 stations / 6 years), which must be declared, not implied by \(n=6\).

---

## 4. Train leakage (climatology / donor \(R^2\) / operator on test years)

**What the year-split scorer actually does** (`river_station_scores`):

- `_year_split`: first 70% of **unique index years**, not leave-one-year (filename is false).
- Operator: `empirical_information_set_conditionals(values[train])`.
- Climatology: one scalar `nanmean(values[train, target])`, not a day-of-year climatology.
- Donor fill: OLS on train, MAE on test.

That path does not average test years into the climatology or into the Schur fit. It is still not the Phase 4 donor-\(R^2\) rule.

**Leakage that is already in the tree, and that Phase 4 will copy if it is not forbidden:**

1. **Empty years pad the 70% cut.** Unique years are taken from the 2000–2024 wide index, including years with almost no concurrent data. Suwannee overlap starts 2019-12-12; train years are 2000–2015+2017. The concurrent window is almost entirely in **test**. Conditionals are estimated on the sparse early years; the only good overlap is the outcome period. Clearwater overlap ends 2021-01-05; test still includes 2022–2024 (the blow-up years). A “fix” that then estimates climatology, ACF, or donor \(R^2\) on all years would move test mass into \(X\).

2. **Synthetic nested table has no year split.** `donor_r2_only` and `conditional_covariance` both use the population \(\Sigma\). \(Y\) is the same \(\Sigma\). There is no fitting-period donor \(R^2\). Freeze `forbidden_as_primary`: `in_sample_donor_r2_without_cv`. Required: `year_block_cross_validated_r2`.

3. **Full-panel covariance is already used on real rivers.** `empirical_river_from_panel` does `DataFrame(values).cov()` on **all** days, then sensor policy. `real_river_sensor_check.csv` is that leak. It is not an ablation, but it is the empirical-\(\Sigma\) recipe sitting next to the scores.

4. **Achieved “skill” is not a 30-day gap.** Predicted columns are 30-day information-set skill. Observed loss is **same-day** donor regression MAE on every finite test day. Stop-loss \(\Delta R^2\) of a gap operator versus a same-day \(R^2\) is a different experiment than the freeze.

**Required method.** Declare calendar train years from the overlap window, not from a padded index. Climatology and donor \(R^2\) from fitting years only; donor \(R^2\) year-block CV. Operator \(\hat\Sigma\) from fitting years only. \(Y\) from held-out **gaps** (artificial or `real_missing_blocks`), not from same-day fill on the years that defined \(\hat\Sigma\). Do not reuse `empirical_river_from_panel`.

---

## 5. Nested \(\Delta R^2\) on 6 in-sample points

`incremental_fit` is in-sample OLS. It returns `nan` when `n <= n_params`. Six network means + intercept + five predictors = six columns, six rows → `nan` or a saturated \(R^2=1\). Thirty station-rows (the six rivers after the peek) still treat stations as independent and use the same rivers that produced 0.77.

The only shipped nested table is the 28-row synthetic identity (attack 1). `paper/next/results.md` does not report a real-river \(\Delta R^2\). It reports the peeked Spearman instead. That is how a missing stop-loss gets replaced by a T2-shaped headline on \(n=6\).

`intended_locks_after_phase_4` still lists `incremental_over` and the T2 floors. If Phase 4 “locks” incremental value from six in-sample points, the leftover protocol hole becomes the lock date.

**Required method.** Nested \(\Delta R^2\) after donor \(R^2\) only, **out of network** (LORO or cluster bootstrap over rivers). Station-rows are repeated measures. If \(\Delta R^2\) versus donor \(R^2\) is \(\approx 0\), retitle; do not add ACF terms, drop Clearwater again, or switch \(Y\) from MAE to skill to rescue a positive increment. Do not lock `incremental_over` from this sample.

---

## 6. Sealed rivers

**Pass on existing files.** `leave_one_year_scores.csv` is only the 12 `never_sealed` rivers. `scripts/47` iterates `build`/`lock`/`development`/`validation` and keeps `DO_NOT_DOWNLOAD` for named sealed Colorado / Columbia / Ohio / Deschutes sites. `framework_manifest.json`: `sealed_outcomes_opened: false`. `paper/next/results.md`: last-check rivers were not scored with temperatures. `data/public_rivers/nwis/` is the burned 12.

**Required method.** Phase 4 must stay on those 12 (or a predeclared input-eligible subset). Do not download sealed catalog IDs to “get past \(n=6\)”. Do not score Loire / Swiss daily. T7 is evaluate-once after the stop-loss is written, not a rescue sample.

---

## Must-fix

1. **Write a real-river ablation or write that Phase 4 did not run.** Do not cite `baseline_nested_r2.csv` / `residual_r2>0` as incremental value. Kill \(X=Y\): `conditional_covariance` cannot equal `observed_structural_skill`. \(Y\) = held-out gap skill; \(X_{\mathrm{op}}\) = fitting-period \(\mathcal R\). Recompute or delete the synthetic last row \(R^2=1.0\).

2. **Predeclare exclusions on inputs.** Apply `complete_enough` (or a written \(n_{\mathrm{eff}}\) / physical-range rule) before scores. Stop dropping Clearwater after MAE \(10^4\). Delete or tombstone `leave_one_river_out_without_clearwater.csv`. Do not keep Suwannee and drop Clearwater under different stories. Do not cite 0.77 or 0.821 as anything but a burned, peeked pilot.

3. **Do not sell \(n=6\) as T2.** No network-level CI from the pilot. No `incremental_over` lock from six rivers. If a development Spearman is shown, name the predeclared set (and that it is not the concurrent-enough six). T2 remains \(n\ge 100\) or an explicit freeze relaxation.

4. **Close leakage.** Fitting-period climatology and year-block-CV donor \(R^2\) only. Split on the overlap window, not on a 2000–2024 index padded with empty years. Do not estimate ACF / donor \(R^2\) / \(\hat\Sigma\) on test years. Do not use full-panel `cov()` as the operator. Score held-out gaps, not same-day donor MAE, if the claim is gap recoverability.

5. **Stop-loss is out-of-network \(\Delta R^2\) after donor \(R^2\).** In-sample OLS on 6 (or 30 nested) points is invalid. If the operator does not beat donor \(R^2\), retitle; do not retune, do not peek another river off, do not swap MAE for skill.

6. **Keep sealed closed.** Phase 4 does not open last-check temperatures. Padding \(n\) with sealed IDs fails this review even if the tautology is fixed.
