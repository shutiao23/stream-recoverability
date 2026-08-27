# RED TEAM: W2 Phase-4 y-specification

Date: 2026-08-26
Role: Implementer B (adversarial). Attack production Phase-4 y only. Not a license to retune, download, or open sealed rivers.
Scope: `src/stream_recoverability/experiments/public_river_operator_ablation.py`, `scripts/56_public_river_operator_ablation.py`, `results/framework/public_rivers/operator_ablation_manifest.json`, `operator_nested_ablation.csv`, `overlap.csv`.
Correct scratch path: `scratch/adversarial/w2/` (this pack). Production `src/`, freeze YAML, and `results/framework/public_rivers/*.json` were not edited.

T2 estimand (locked): Spearman\((\hat{\mathcal R}, \text{gap-specific achieved skill})\). W2 is a six-river **pipeline verification**, not T2. Freeze / protocol v9.1: manifest must write `n_networks: 6`, `passed: false`, `purpose: pipeline_verification_not_evidence`. The pipeline check is nonzero gap_length \(\Delta R^2\) on a **pooled** 30/90 table and different first rows at L=30 vs L=90, not “did the operator win.”

---

## Verdict

Production still scores **later-year same-day donor-regression skill once per station** and **copies it across gap lengths**. Nested OLS is then split per gap so gap_length \(\Delta R^2\) is vacuously 0 inside each table. The honest flag `achieved_skill_is_later_year_not_gap_specific: true` is on disk; that does not make the table a W2 check.

Delaware (`complete_enough=True`, 8857 concurrent days) is `could_not_score_any_station` because later-year MAE requires **every** donor on the same test day (Delaware has **0** all-seven days). Suwannee (`complete_enough=False`) leaked into `scored_networks`. `n_networks` is 5 survivors, not the predeclared six.

Flipping the flag to `false` without changing y is a lie. Holes 1–3 still ship.

---

## 1. Copied later-year y (T2 estimand is Spearman\((\hat R, \text{gap-specific skill})\))

**Naive.** `station_operator_rows` computes `donor_regression_mae` and scalar-climatology MAE on the full later-year test mask **once**, then:

```python
achieved = recoverability(donor_mae, climate_mae)
for gap_length in gap_lengths:
    rows.append({..., "gap_length": gap_length, "achieved_skill": achieved})
```

`X` (`recoverability_r`, heuristic) depends on L. `Y` does not. Manifest: `achieved_skill_is_later_year_not_gap_specific: true`. Spearman-by-gap can still move (0.90 vs 0.70 on disk) because \(\hat{\mathcal R}\) moved, not because skill is a 30-day or 90-day fill.

**Required.** Plant observed blocks of length 30 and 90 in later years. Fit donors and day-of-year climatology on **train years only**. Score fill MAE vs climatology **on the planted block**. `Y(L=30) \neq Y(L=90)` except by accident. Scratch: `gap_specific_scorer.planted_station_rows`.

**Flag-only weasel.** Setting the flag to `false` while leaving this loop ships the same copied y. Tests: `test_production_later_year_y_identical_across_l`, `test_flag_only_does_not_fix_copied_y`.

---

## 2. Per-gap nested grids as a weasel that makes gap_length \(\Delta R^2\) undefined/zero

**Naive.** `run_public_river_operator_ablation` loops `for gap in gap_lengths` and calls `nested_ablation_table` on `_rows_for_gap(...)`. On-disk `operator_nested_ablation.csv`: every `added=gap_length` row is `r2=0.0, delta_r2=0.0`. Manifest excuse: `"nested_grids": "separate per gap so later-year skill is not duplicated"`.

Inside one gap, `gap_length` is a constant. The first nested step has no X-variation. \(\Delta R^2=0\) is vacuous. It cannot be the W2 pipeline check (nonzero gap_length \(\Delta R^2\)). Pooling copied later-year y would still give \(\Delta R^2 \approx 0\), which is the **honest** diagnosis that y does not depend on L. Splitting hides that diagnosis behind a constant column.

**Required.** One nested table on the **pooled** 30∪90 rows. Pipeline pass = gap_length \(\Delta R^2 \neq 0\) **and** first L=30 vs L=90 rows differ. Operator \(\Delta R^2\) is not the criterion and does not license retuning. Per-gap tables may be shown as a diagnostic; they must not be the check.

**Flag-only weasel.** Flag false + still-split grids still ships a vacuous zero. Tests: `test_pooling_gaps_required_for_gap_length_delta_r2`.

---

## 3. Delaware swapped for Suwannee

**Naive.** `overlap.csv` `complete_enough` six: Delaware, Willamette, Madison, Mahoning, Roanoke, Santa Fe. Delaware: 8857 concurrent days, `complete_enough=True`. Suwannee: 1648 days, 5.05 overlap years, `complete_enough=False`.

Production later-year MAE uses `np.isfinite(x_test).all(axis=1)` (all donors present). Delaware has **zero** days with all seven stations. Every station returns NaN MAE → `could_not_score_any_station`. `load_public_river_panels` still loads Suwannee. `scored_networks` = Madison, Mahoning, Roanoke, Santa Fe, **Suwannee**, Willamette. `delaware_scored: false`. `n_networks: 5`. `requested_primary_missing: [delaware_river_huc20]`.

**Required.** Roster is the six `complete_enough` IDs. Suwannee must not replace Delaware. Fill may use **usable** donors (train overlap; not the full catalog on one day). Sparse columns (Delaware `01427301` has 0 later-year days; `01434000` is almost only later-year) are not a license to drop the network. Scratch `usable_donor_indices` is the required donor rule.

**Flag-only weasel.** Flag does not restore Delaware or eject Suwannee. Tests: `test_six_concurrent_enough_ids_suwannee_is_not_delaware`, `test_delaware_all_donor_constraint_is_the_later_year_failure`.

---

## 4. Reporting cluster-bootstrap CI at n=6 as `tested`

**Naive.** `network_bootstrap_spearman` still emits `inference_status: "tested"` once `n >= min_networks_for_interval` (default 100 in the current call, 5 in older on-disk checks). `evaluate_success` treats `tested` as a CI pass ingredient. Freeze: 12-river pilot, 6-river W2 redo, and any n<100 stop-loss **must not report a network-level interval**. Historical `public_river_check.json` already shipped a 5-river “tested” CI.

**Required.** W2 manifest `network_interval.inference_status = withheld_n_lt_100_network_interval`, `ci_lower`/`ci_upper` null. Never write `tested`. `evaluate_success.passed` stays false. `n_networks_min` stays 100.

**Flag-only weasel.** Unrelated to y, but a flag-only “W2 done” PR that then quotes a six-river CI still ships this hole. Contract: `manifest_contract.json`.

---

## 5. `passed: true` or selling W2 as T2 / formal_evidence / headline

**Naive.** Production currently keeps `formal_evidence: false` and `evaluate_success.passed: false`, but `n_networks: 5`, `operator_incremental_r2_le_0: false`, and a positive station \(\Delta R^2\) (0.162) are one paragraph away from a stop-loss “win.” Master-plan Phase 4 already quotes those numbers. W2 protocol text forbids treating operator win/loss as the pipeline criterion.

**Required.** `passed: false`, `purpose: pipeline_verification_not_evidence`, `formal_evidence: false`, `headline_claim_licensed: false`, `confirmatory_eligible: false`. Pipeline criterion = pooled gap_length \(\Delta R^2\) and differing L rows. Do not rename W2 as T2 because Spearman looks large.

**Flag-only weasel.** A false y-flag plus `passed: true` is worse. Keep `passed: false` even if planted y and pooled \(\Delta R^2\) look pretty.

---

## 6. Overwriting `results/framework/public_rivers/operator_ablation_manifest.json`

**Naive.** `scripts/56` writes the later-year audit to that path. A “fix y” patch that overwrites it destroys the labeled later-year record (`achieved_skill_is_later_year_not_gap_specific: true`, Delaware missing, Suwannee leaked).

**Required.** Leave the production later-year audit in place. W2 planted artifacts go under a new filename or under `scratch/adversarial/w2/outputs/`. This pack sets `overwrites_later_year_audit_manifest: false`.

---

## 7. Retuning operator / twin / φ because incremental \(R^2 \le 0\)

**Naive.** Stop-loss language: if the operator adds nothing after donor \(R^2\), retitle to predictability. The forbidden move is to retune the Schur operator, the twin generator, or φ until \(\Delta R^2 > 0\), or to switch y from MAE to skill, drop a river after seeing °C, or un-pool gaps until a positive step appears. Production currently reports a **positive** increment on copied later-year y; that number is not a license either.

**Required.** Write the pooled planted-gap increment honestly. If \(\le 0\), retitle; do not retune. `operator_incremental_r2_le_0_does_not_license_retuning: true`. No `design_freeze_v4` retarget. No twin generator edits. This pack did neither.

---

## 8. Downloading the 98 name×HUC2 list or new temperatures

**Naive.** n=5 scored / n=6 roster looks small. Padding with catalog v2/v3 downloads, Hub'Eau, or UK EA does not make W2 into T2 and is forbidden for this redo.

**Required.** Already-downloaded `*_daily_wide.csv` only. `new_temperatures_downloaded: false`, `catalog_98_name_huc2_downloaded: false`. This pack does not call NWIS.

---

## 9. Opening sealed / Jinsha / Chattahoochee confirmatory outcomes

**Naive.** Last-check temperatures or historical confirmatory JSON as extra y would peek T7/T2.

**Required.** `sealed_outcomes_opened: false`, `jinsha_outcomes_used: false`, `chattahoochee_outcomes_used: false`. W2 stays on burned public rivers.

---

## 10. Using natural-outage `fill_mae` from script 59 as if it were the W2 planted 30/90 grid

**Naive.** `natural_outage_scores.csv` already has planted-gap `fill_mae` (T4 geometry from `real_missing_blocks.csv`, lengths 7/9/31/91/…). That is T3b/T4, not Phase-4 y. Lengths are empirical and seasonal, not the W2 30/90 grid. Mixing them “because they are gap-specific” launders a different task into W2.

**Required.** Plant a **regular 30/90** grid on later-year observed days. Train-only predictors. Do not read script-59 scores as W2 y. `natural_outage_fill_mae_used_as_phase4_y: false`.

---

## Extra hole (ships with 1–3): n_networks counted as scored survivors

Production `n_networks` is `complete["network_id"].nunique()` after Delaware fails (5), not the predeclared concurrent-enough roster (6). W2 contract is `n_networks: 6` as the roster size. Do not let a 5-row nested table satisfy the freeze sentence.

---

## If production only sets the flag to false

Still ships:

| # | Hole | Why the flag is not a fix |
| --- | --- | --- |
| 1 | Copied later-year y | The loop still copies `achieved`. Flag becomes a lie. Pooled gap_length \(\Delta R^2\) stays ~0. |
| 2 | Per-gap nested weasel | Unchanged split; vacuous zero remains. |
| 3 | Delaware / Suwannee | Scoring rule and panel filter unchanged. |
| 4 | `tested` CI at n=6 | Flag does not withhold CIs. |
| 5 | Selling as T2 | Flag does not force `passed: false` / `purpose`. |
| 6 | Overwriting the later-year audit | A “fix” commit that rewrites the same JSON path still does this. |
| 7–10 | Retune / download / sealed / T4 fill_mae | Orthogonal; still forbidden. |

Holes 1, 2, and 3 **will still ship** under a flag-only patch. That is the merge blocker.

---

## Naive vs required (one line each)

| | Naive (in tree) | Required (this pack) |
| --- | --- | --- |
| y | Later-year same-day donor MAE, copied across L | Planted L=30 and L=90 fill MAE vs train DOY climatology |
| Nested | Separate `gap_30` / `gap_90` tables | Pooled 30∪90; per-gap is not the check |
| Roster | 5 scored + Suwannee leak | Six `complete_enough` IDs; Delaware in, Suwannee out |
| Donors | All catalog columns finite on the same day | Usable donors with train overlap |
| Manifest | n=5, flag true, later-year prose | n=6, `passed: false`, `purpose: pipeline_verification_not_evidence`, flag false, no `tested` CI |
| Audit file | One JSON for everything | Keep later-year `operator_ablation_manifest.json`; W2 writes elsewhere |

---

## Merge instructions for parent

1. **Do not overwrite** `results/framework/public_rivers/operator_ablation_manifest.json`. That file is the later-year audit (`achieved_skill_is_later_year_not_gap_specific: true`). W2 artifacts: new names or `scratch/adversarial/w2/outputs/`.
2. Port `scratch/adversarial/w2/gap_specific_scorer.py` as the W2 y-path. Keep `station_operator_rows` labeled as the later-year hole, or call it only from an audit script.
3. Nested \(\Delta R^2\) for the pipeline check must use the **pooled** 30∪90 table. Do not treat per-gap `delta_r2=0` as a pass or as evidence that gap length does not matter.
4. Roster = `concurrent_enough` six from `overlap.csv`. Do not score Suwannee as a Delaware substitute. Use usable-donor fill so Delaware can be scored without requiring all seven columns on one day.
5. Copy keys from `scratch/adversarial/w2/manifest_contract.json`. `n_networks: 6`, `passed: false`, `purpose: pipeline_verification_not_evidence`, `achieved_skill_is_later_year_not_gap_specific: false` **only after y is planted**. `network_interval.inference_status` must not be `tested`.
6. Pipeline criterion: pooled gap_length \(\Delta R^2 \neq 0\) and first L=30 vs L=90 rows differ. Not operator \(\Delta R^2\). If operator increment \(\le 0\), retitle; do not retune operator/twin/φ; do not touch `design_freeze_v4`.
7. No new USGS downloads. No sealed / Jinsha / Chattahoochee outcomes. No 98-name catalog harvest. No T4 `natural_outage_scores.csv` as Phase-4 y.
8. **Reject a patch that only sets the flag to false.**

---

## Pack layout

| Path | What |
| --- | --- |
| `scratch/adversarial/w2/REDTEAM.md` | This memo |
| `scratch/adversarial/w2/gap_specific_scorer.py` | Correct planted 30/90 scorer (imports production helpers) |
| `scratch/adversarial/w2/test_w2_phase4_y.py` | Holes 1–3, pooling, roster, contract, flag-only |
| `scratch/adversarial/w2/run_w2_demo.py` | Toy CSV/JSON; `--six-rivers` writes scratch outputs only |
| `scratch/adversarial/w2/demo/later_year_vs_gap_specific.csv` | First rows: later-year match, planted differ |
| `scratch/adversarial/w2/demo/later_year_vs_gap_specific.json` | Same |
| `scratch/adversarial/w2/manifest_contract.json` | Required W2 keys |
| `scratch/adversarial/w2/outputs/` | Six-river planted scores/manifest (scratch only; Delaware in, Suwannee out) |

## Scratch run (already-downloaded wides only)

`PYTHONPATH=src python scratch/adversarial/w2/run_w2_demo.py --six-rivers`

- Toy first rows: later-year skill **identical** at L=30/90 (`0.7437`); planted skill **differs** (`0.753` vs `0.022` on the shocked target).
- Six `complete_enough` rivers scored under scratch: **Delaware recovered** (usable donors; 4 donors/station). `requested_primary_missing: []`. Suwannee not scored.
- 62 station×gap rows. Pooled gap_length \(\Delta R^2 = 7.9\times 10^{-5}\) (nonzero, so not the vacuous per-gap zero). Operator increment on this planted y is \(+0.052\); **not T2**, `passed` stays false.
- Production `operator_ablation_manifest.json` still has `achieved_skill_is_later_year_not_gap_specific: true` and `delaware_scored: false`. It was not overwritten.

Same-day donor fill is gap-specific in the **window** sense (different days) but only weakly gap-specific in the **information-set** sense (no boundary interpolation). That is why real-river pooled \(\Delta R^2\) is tiny. Do not “fix” it by retuning φ, by splitting tables again, or by substituting T4 `natural_outage_scores.csv`. A later fill that actually uses \(B\cup D\) would be a different, declared y — not a silent rescue.

---

Sealed temperatures were not opened. Twin generator was not edited. Freeze YAML was not retargeted.
