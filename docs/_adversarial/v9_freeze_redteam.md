# RED TEAM: v9 freeze, second pass (merged files)

Date: 2026-08-26
Status: leftovers only. Parent decisions are not re-opened.
Target: current `configs/design_freeze_v9.yaml` + current loaders/tests.

Parent already accepted: keep the v9 filename; keep Spearman 0.60; keep CI floor 0.40; burn the 12 downloaded rivers plus Jinsha/Chattahoochee; Loire/Swiss excluded from T8 / non-NA sealed counts until daily history is public; `evaluate_success` reads the freeze.

This pass does **not** demand a rename, unlocked numbers, or un-burning those rivers.

YAML parse: `yaml.safe_load` succeeds (46 keys, no tabs, no undefined aliases). `load_study_freeze()` default path is now v9 and returns `design_id: design_freeze_v9`. Legacy v1 still loads. `DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION` remain v4.

---

## What is no longer a finding

- File exists and is loadable as a study freeze.
- `scripts/45_validate_research_charter.py:39-66` asserts v9, 0.60, 0.40, and a never-sealed subset.
- `study_freeze.py:11` default is `configs/design_freeze_v9.yaml`.
- `governance.next_study_status` prefers v9 (`governance.py:431-438`).
- Burned IDs are in `split_rule.never_sealed_networks` (`design_freeze_v9.yaml:136-150`) and the loader refuses a v9 document that drops them (`study_freeze.py:58-77`).
- T1–T7 blocks, Oh & Bartos name, `placements_per_cell_min: 20`, deep-model roster, and Loire/Swiss exclusion list are present as YAML keys.
- `evaluate_success` loads the freeze and sets `thresholds_locked` from `locked_success_criterion.status` (`hierarchical_confirmation.py:163-170,202`). A live call returns `thresholds_locked=True`.

---

## Leftover 1 — `evaluate_success` reads two floors and ignores the rest

`evaluate_success` (`hierarchical_confirmation.py:163-199`) reads only:

- `locked_success_criterion.t2_large_sample_primary.out_of_network_spearman_min`
- `locked_success_criterion.t2_large_sample_primary.network_bootstrap_lower_bound_min`
- `locked_success_criterion.status` (for the boolean)

It does **not** read these locked machine fields, which exist in the freeze:

| Freeze field | Where | What the executor does |
| --- | --- | --- |
| `inference.n_networks_min: 100` | `design_freeze_v9.yaml:194` | Ignored. An 8-network synthetic panel is scored as `inference_status: tested` and *can* return `passed: True`. |
| `minimum_independent_networks_for_interval: 100` | `yaml:114` | Ignored. `network_bootstrap_spearman` still withholds CIs only when `len(networks) < 5` (`hierarchical_confirmation.py:56-62`). |
| `ci95_lower_bound_must_exceed: four_preregistered_univariate_baseline_point_estimates` | `yaml:199` | String token. No baseline scores are accepted or compared. |
| `sealed_skill_median_absolute_bias_max` / `calibration_slope_min` / `calibration_slope_max` | `yaml:200-202` | Ignored. |
| `management.leave_one_network_out_same_sign_majority` / `single_network_may_not_drive` | `yaml:216-217` | Same-sign is a function argument default, not a freeze read. Jackknife is always applied. |
| All T3 placement / triage numbers | `yaml:206-207,293-315` | Ignored. |

Parent said the executor reads the freeze. It reads **two scalars**. The second CI rule and the n≥100 interval rule are still comments as far as the code is concerned. A confirmatory “pass” below 100 networks is still representable.

Callers that inherit this hole:

- `tests/test_science_record_and_outage.py:69` — `evaluate_success(panel)` on 8 synthetic networks; asserts `n_networks == 8` and `"passed" in result`, not that n<100 cannot pass.
- `scripts/44_run_recoverability_framework.py:53` — writes `synthetic_confirmation_passed` from the same 8-network helper.
- `src/stream_recoverability/experiments/real_river_checks.py:142` — LORO of the burned 12.

---

## Leftover 2 — tests / artifacts still treat thresholds as unlocked

No pytest asserts `thresholds_locked is False`. The leftover is the opposite hole plus a stale machine artifact.

- `results/framework/public_rivers/public_river_check.json:20` still has `"thresholds_locked": false` (written by `scripts/47_download_and_check_build_rivers.py:175-179` from whatever `evaluate_success` returned at download time). Live `evaluate_success` now returns `True`. The on-disk check file is the old contract.
- `tests/test_science_record_and_outage.py:69-71` does not assert `result["thresholds_locked"] is True`. Reverting `hierarchical_confirmation.py:170` to a hardcoded `False` would not fail CI.
- `results/framework/framework_manifest.json:9` still records `"design_id": "recoverability_study_freeze_v1"`. `scripts/44_run_recoverability_framework.py:83` would write `design_freeze_v9` if re-run; the checked-in manifest is v1 provenance.

---

## Leftover 3 — historical pipeline collision is the `design_version` field, not the filename

Parent kept the filename. The leftover is that the study freeze also sets the **historical identity key**:

```1:2:configs/design_freeze_v9.yaml
design_id: design_freeze_v9
design_version: design_freeze_v9
```

`DEFAULT_DESIGN_PATH` is still `configs/design_freeze_v4.yaml` (`contracts.py:15-19`). Good. There is no `not_an_executable_design` / `executable: false` machine field.

If any historical loader is pointed at this file:

- `load_confirmatory_protocol` (`src/stream_recoverability/data/confirmatory.py:513-522`) raises `design_version must be design_freeze_v2, v3, or v4, got 'design_freeze_v9'`. That error reads as “unknown executable version,” not “this is the next-paper study freeze.”
- `load_frozen_data_versions` (`contracts.py:68-76`) raises `TypeError: design freeze data_versions must be a mapping` (v9 has no `data_versions`).
- `build_design_contract` (`contracts.py:465-471`) would take `design["design_version"]` then `KeyError` on `mask_design` / `training` schema versions.
- `governance.evidence_snapshot` / `submission_gate` (`governance.py:194,289-290`) compare `design_version` to `EXECUTABLE_DESIGN_VERSION`. A retarget to this path blocks submission (fail-closed) **or**, if someone “fixes” the mismatch by adding `design_freeze_v9` to `SUPPORTED_EXECUTABLE_DESIGN_VERSIONS` (`contracts.py:16-18`), the 134k-run pipeline is the casualty.

Dummy mismatch tests still mutate a contract to `"design_freeze_v9"` (`tests/test_reference_runner.py:312`; `tests/test_formal_registry_builder.py:935`). That remains safe only while executable stays v4. The YAML `design_version` field is what makes a later retarget look like the v1→v2→v3→v4 ritual.

v9 has no `data_versions`, `evidence_contract`, `training`, or `formal_model_candidates`. Fail-closed today. No explicit guard says “study freeze; refuse as executable design.”

---

## Leftover 4 — two success blocks, loader only pins one

`REQUIRED_KEYS` still requires `provisional_success_criterion` (`study_freeze.py:20`) and does **not** include `locked_success_criterion` (that key is checked only when `design_id`/`design_version` is already v9, `study_freeze.py:45-57`).

The two blocks already disagree on key names:

- Locked T2 uses `out_of_network_spearman_min` (`yaml:197`).
- Provisional copy uses `network_blocked_spearman_min` (`yaml:230`).
- Locked-only: `gates_are_confirmatory_floors`, `development_power_analysis_may_only_raise`, `six_river_pilot_is_failed_context_not_evidence`.
- Provisional-only under `intended_locks_after_phase_4`: `incremental_over`, `leave_one_network_out_same_sign_majority`, `single_network_may_not_drive`.

Loader checks Spearman ≥ 0.60 and CI floor ≥ 0.40 on the **locked** block only. The provisional copy can drift without failing `load_study_freeze` or script 45.

---

## Leftover 5 — remapper and catalog still ignore the burned-river machine field

`scripts/51_apply_catalog_clusters.py:70,91-95,106-107` still rebuilds development/validation from cluster CSV order, sets `historical_seen: False` on every new row, and keeps only `historical_seen` or `use == last_check`. It does not read `split_rule.never_sealed_networks`. Re-running `make apply-catalog-clusters` can reassign a burned `use: build` / `use: lock` river. The freeze forbids sealing them (`yaml:132`) but no script enforces that field.

`scripts/45_validate_research_charter.py:57-63` only checks that four of the fourteen burned IDs are present. The loader has the full set (`study_freeze.py:59-74`); the charter gate does not.

Catalog validator still requires 4 stations and 4 climate classes (`src/stream_recoverability/data/network_catalog.py:62-63,81-82`). Freeze locks 3 and 3 (`yaml:166-173`) and documents `known_contract_lag`. Script 45 still runs `validate_catalog` (`scripts/45_validate_research_charter.py:70-72`). A Phase 3 3-station network fails the Phase 0 gate. No `auto_reassign_from_fractions: false` field. No per-network `continent` field, so `continents_min: 2` (`yaml:174`) cannot be validated.

---

## Leftover 6 — named policies that no executor implements

Freeze `sensor_policy.strategies` and T3(a) `non_oracle_baselines` name `degree` and `oh_bartos_2025_rank_revealing_qr` (`yaml:298-302,398-408`).

`POLICIES` in `src/stream_recoverability/experiments/sensor_policy.py:231-239` is still:

`random`, `spatially_even`, `distance`, `correlation_redundancy`, `observability_gramian`, `proposed_recoverability`, `oracle`.

Grep for `oh_bartos` / `policy_degree` in that module: zero. The machine field exists; the decision test cannot fail closed against it.

---

## Leftover 7 — still-missing machine fields

Present as prose or a boolean, not as something a future script can check:

- `not_an_executable_design` / `executable: false` (see leftover 3).
- `auto_reassign_from_fractions: false` (see leftover 5).
- `t8.public_sources: [usgs, hubeau, foen, uk_ea]` and a countable-vs-excluded flag that catalog validation can use. Loire/Swiss are listed (`yaml:151-153`); UK EA is not a field. `continents_min` has no catalog column (`network_catalog.py` has no `continent`).
- `t7_sealed_confirmatory` (`yaml:287-291`) says `numeric_thresholds_preregistered: true` but does not copy the T2/T3 numbers. Evaluate-once has no hash / once-lock path field.
- `ci95_lower_bound_must_exceed` is not a list of baseline names plus a comparison operator. `evaluate_success` cannot implement leftover 1 without that shape.
- `theory_propositions.gaussian_mae_factor` matches `GAUSSIAN_MAE_FACTOR` today (`conditional_observability.py:17` = `0.7978845608028654`) but no loader asserts equality.

No YAML syntax error remains.

---

## Caller grep (current)

`load_study_freeze` / `DEFAULT_STUDY_FREEZE`:

- `src/stream_recoverability/analysis/study_freeze.py:11,30,82`
- `src/stream_recoverability/analysis/hierarchical_confirmation.py:11,163`
- `src/stream_recoverability/governance.py:20-21,434-439`
- `scripts/44_run_recoverability_framework.py:25,42`
- `scripts/45_validate_research_charter.py:15,39`
- `tests/test_network_catalog_and_charter.py:7,24,39,44`

`design_version: design_freeze_v9` collision surface:

- `configs/design_freeze_v9.yaml:2`
- `tests/test_reference_runner.py:312`
- `tests/test_formal_registry_builder.py:935`
- `src/stream_recoverability/data/confirmatory.py:513-522` (rejects it)
- `src/stream_recoverability/experiments/contracts.py:15-19` (executable still v4)

`thresholds_locked`:

- `hierarchical_confirmation.py:170,202` — now `True` when v9 `status` starts with `locked`
- `results/framework/public_rivers/public_river_check.json:20` — still `false`
- no pytest assertion

---

## Must-fix leftovers

1. **Wire the unread T2 locks or stop claiming the executor reads the freeze.** `evaluate_success` must fail closed when `n_networks < 100` before reporting a confirmatory pass or a network-level CI (`design_freeze_v9.yaml:114,194` vs `hierarchical_confirmation.py:56-62,187-199`). Implement `ci95_lower_bound_must_exceed` as a real comparison (needs baseline point estimates in the call), or delete the token. Calibration slope / median bias must either be checked or explicitly marked `not_evaluated_by_evaluate_success`.

2. **Pin `thresholds_locked is True` in a test.** `tests/test_science_record_and_outage.py:69-71` is the existing caller and does not. Refresh or tombstone `results/framework/public_rivers/public_river_check.json:20` so it cannot be cited as the unlocked contract.

3. **Remove or quarantine `design_version` on the study freeze.** Keep the filename. Drop `design_version: design_freeze_v9` (`configs/design_freeze_v9.yaml:2`) or add `not_an_executable_design: true` and make `load_confirmatory_protocol` / `load_frozen_data_versions` / `build_design_contract` refuse this path with a study-freeze message. Do not add `design_freeze_v9` to `SUPPORTED_EXECUTABLE_DESIGN_VERSIONS` (`contracts.py:16-18`). Leave dummy test strings as-is.

4. **One success block.** Either drop `provisional_success_criterion` from `REQUIRED_KEYS` (`study_freeze.py:20`) now that `locked_success_criterion` exists, or make the loader assert the two blocks cannot drift (`yaml:185-252` already disagree on Spearman key names).

5. **Make `never_sealed_networks` executable.** `scripts/51_apply_catalog_clusters.py:91-107` must not reassign those IDs. Script 45 should assert the full burned set, not four IDs (`scripts/45_validate_research_charter.py:57-63` vs `study_freeze.py:59-74`). Add `auto_reassign_from_fractions: false`.

6. **Implement or un-name `oh_bartos_2025_rank_revealing_qr` and `degree`.** They are in the freeze (`yaml:302,406`) and absent from `sensor_policy.py:231-239`. A named T3(a) baseline that cannot run is not a lock.

7. **Add the still-missing fields:** `executable: false`; T8 `public_sources`; a catalog `continent` (or T8 countable flag); T7 copy of the numeric thresholds plus an evaluate-once path. Re-run script 44 so `results/framework/framework_manifest.json:9` is not left on `recoverability_study_freeze_v1`.
