# RED TEAM pass 2: merged v8→v9 protocol

Date: 2026-08-26
Role: leftover holes only. Parent-accepted decisions are not re-opened.
Target: the merged `docs/protocol_change_v8_to_v9.md`, `configs/design_freeze_v9.yaml`, and `docs/research_charter_v1.md`.
Not a result. Sealed temperatures were not opened.

## Parent decisions this pass does not re-litigate

Keep Spearman ≥ 0.60 locked as a confirmatory floor. Keep **both** CI rules (0.40 floor **and** four-baseline point-estimate rule). Keep the filename `configs/design_freeze_v9.yaml`. Burn the 12 downloaded rivers plus Jinsha / Chattahoochee. Loire / Swiss do not count toward T8 or the ≥10 non-NA sealed set. B1/S2 are not formula-forced. One sealed absolute floor: 40. `formal_evidence` stays false until once-open. 150 remains a target, not a current inventory.

Those are in the merged text. The holes below are where the merge **failed to make them executable**, or where two locked documents still disagree.

---

## Verdict

The merged protocol is a real freeze on paper. It is not a closed Phase 0 contract. The parent-accepted four-baseline CI rule is YAML prose only: `evaluate_success` never scores it. Network CIs still open at **5** rivers while the freeze forbids reporting below **100**. Protocol T1–T8 still “follow” a master-plan block that was **not** updated (no 0.40 floor; sealed still “30–40”). T3(b) is 0.05 in the YAML and “例如 5%” in the protocol and charter. `csdi_or_grin` is a one-slot OR. `provisional_success_criterion.intended_locks_after_phase_4` is still a second lock calendar. Charter §河怎么分 never writes the Loire/Swiss exclusion. Colorado and Columbia can still pad the sealed 40 without an 8-year overlap.

---

## Leftover 1 — Four-baseline CI rule is not implemented

Parent: lock both CI rules. Freeze does:

```yaml
network_bootstrap_lower_bound_min: 0.40
ci95_lower_bound_must_exceed: four_preregistered_univariate_baseline_point_estimates
```

`src/stream_recoverability/analysis/hierarchical_confirmation.py` `evaluate_success` reads only `out_of_network_spearman_min` and `network_bootstrap_lower_bound_min`. `passed` never compares `ci_lower` to the four univariate **point estimates**. No function in `src/` reads `ci95_lower_bound_must_exceed`. `load_study_freeze` and `scripts/45_validate_research_charter.py` do not require that key.

A sealed run can beat 0.60 and 0.40, lose to donor-\(R^2\)-only on the point estimate, and still print `passed: true`. That is the parent rule, unenforced.

**Must-fix:** define the four baseline Spearman point estimates on the same out-of-network split; make `evaluate_success` fail if `ci_lower` is not above all four; pin the key in the loader and in script 45.

---

## Leftover 2 — CI floor is 5 in code, 100 in the freeze

Freeze:

- `minimum_independent_networks_for_interval: 100`
- `interval_rule`: primary CIs require ≥100 networks
- protocol §6: 只有独立河网数 ≥100 才允许报告置信区间

`network_bootstrap_spearman` still withholds only when `len(networks) < 5`. That is the historical BL-012 site-year floor, not the v9 network floor.

Worse: `evaluate_success` treats a non-`tested` interval as a **pass**:

```text
inference_status != "tested"  OR  (ci_lower > 0.40)
```

So n < 5 can pass T2 on the point estimate alone. n = 6..99 will **report** a CI and can pass T2, against the freeze’s “do not report a network-level interval from the 12-river pilot / below 100.”

**Must-fix:** withhold network CIs unless n ≥ 100; `evaluate_success` must not pass when the interval is withheld or n < 100. Keep the nested floor of 5 as a within-network descriptive rule only, as the freeze already claims.

---

## Leftover 3 — Protocol still points T1–T8 at an unpatched master plan

Protocol §7:

> T1…T8 仍按 `docs/v9_redesign_master_plan.md` 执行。

The master-plan **Locked gates** block was not rewritten after the parent merge:

- T2 still omits the 0.40 CI floor (only the four-baseline rule).
- T7 still says sealed `≥ 30–40`.
- Split still says “19-network catalog.”

If later phases treat the master plan as the gate list, the merge’s “both CI rules” and “one floor: 40” can be dropped by citation. Parent review at the bottom of that file does **not** override the Locked gates section unless someone says so.

**Must-fix:** either update the master-plan T2/T7/split lines to match the merge, or delete the “仍按 master plan 执行” sentence and make the protocol + `design_freeze_v9.yaml` the only gate list.

---

## Leftover 4 — T3(b) is locked in YAML, hedged in the protocol

Freeze `decision_endpoints.b_gap_triage`:

- `false_release_rate: 0.05`
- `false_release_definition: fill_error_gt_0.5_degC`
- `safe_fill_relative_improvement_min: 0.30`
- `safe_fill_absolute_improvement_min_pp: 15`

Protocol §7 T3(b) and charter “怎样算过关” still say **例如 5%**. That is the v8 empty-freeze move on the preferred headline. Evaluate-once cannot have an “e.g.” on the operating point.

**Must-fix:** protocol and charter must say the locked 5% / 0.5°C / 30% / 15 pp numbers, or point at the YAML keys and forbid a different rate after seeing the ROC.

---

## Leftover 5 — `csdi_or_grin` is a one-slot OR

Protocol: “SAITS 与 CSDI（或 GRIN）留在 roster.”  
Freeze `required_recovery_models` has `saits` and `csdi_or_grin`.

CSDI can be dropped for GRIN without a BL. That repeats the v5 class-exclusion pattern the merge claimed to close (`primary_evidence_forbids: excluding_models_because_best_epoch_lt_50`).

**Must-fix:** two roster lines (`csdi` and `grin`), or a written compute-bound BL that names which one is absent and forbids a model-class claim about the missing one.

---

## Leftover 6 — Two lock calendars

`locked_success_criterion.status: locked` is the parent merge.  
`provisional_success_criterion` is still a `REQUIRED_KEYS` entry, status `locked_by_v9`, with **`intended_locks_after_phase_4`** listing the same T2 numbers.

A later editor can treat Phase 4 as the lock moment and “raise or replace” the floors. `load_study_freeze` does not require `locked_success_criterion` except when `design_id`/`design_version` is already `design_freeze_v9`.

**Must-fix:** drop `intended_locks_after_phase_4`, or rename the leftover block so it cannot be read as a second lock date. Keep `provisional_success_criterion` only if the loader treats it as a superseded alias.

---

## Leftover 7 — Loire / Swiss rule is missing from the charter split

Parent accepted: they do not count toward T8 or the ≥10 non-NA sealed set.

Freeze `not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public` and protocol §8 have the rule. Charter **河怎么分** only says “至少 10 条不在北美.” It never names Loire / Swiss as uncountable. `load_study_freeze` does not require that list. Script 45 does not assert it. The list can be deleted and the charter still “holds.”

**Must-fix:** write the exclusion in charter §河怎么分; pin both IDs in the loader and in script 45 the same way `never_sealed_networks` is pinned.

---

## Leftover 8 — Colorado / Columbia can pad the sealed 40

Parent closed Loire / Swiss. It did not close the other sealed rows that already fail T2.

`network_catalog_v1.yaml`: `colorado_grand_canyon` and `columbia_mainstem` are `split_role: sealed` with `catalog_stations_no_common_overlap`. They have no eight-year common window. They are **not** on the not-countable list. Phase 3 can count them toward `sealed_min_networks: 40` while they remain T2-ineligible.

Ohio and Deschutes are `metadata_only_not_downloaded`. Same pad risk.

**Must-fix:** a sealed row counts toward 40 only if it is T2-eligible (or a dated public-daily exception). Put Colorado and Columbia on an explicit `not_countable_toward_sealed_floor_until_overlap` list, or drop them from `sealed` when the catalog is next touched. Phase 0 promised not to remap roles; it did not promise those rows would count.

---

## Leftover 9 — `core_question` is the contribution written as fact

Freeze `core_question` is the master-plan one-sentence contribution, including “transfers across continents” and “beats length-only operations.” Charter 人话 says the same as what the paper **will prove**. Protocol §2 title thesis is the same sentence.

The note says the 12-river numbers are not confirmatory. The question field still reads as an achieved claim. That is how a freeze leaks into an abstract.

**Must-fix:** rewrite `core_question` as a testable question. Keep the contribution sentence only under an explicit `target_not_achieved` key.

---

## Leftover 10 — Station ≥3 vs catalog ≥4 is still an executable trap

Freeze `known_contract_lag` admits the catalog validator still requires 4 stations and 4 climates. T2 / charter lock 3 stations and 3 climates. Script 45 still calls `validate_catalog` and fails the catalog on ≥4.

Documenting the lag is not resolving it. The first 3-station (or 3-climate) Phase 3 add will fail the Phase 0 pass gate. The <100 failure hatch (“relax to 3 stations / 6 years”) is already the T2 station floor; the only remaining hatch is **8 → 6 years**, which the lag note does not mention.

**Must-fix:** one integer in charter, T2, freeze, and `validate_catalog`, or a Phase 3 ticket that script 45 will refuse to pass until the validator matches the freeze. Do not ship a gate that must be broken to use the scientific target.

---

## Other omissions (not re-opened parent fights)

These were on the first-pass missing list and are still absent. They are leftovers, not new theory.

- Johnson et al. 2021 (`johnson2021datagap`) is still not a required citation or T4/T6 bridge.
- T6 is still “preferred: SEPlains × BFI,” so a friendlier failure zone can satisfy T6.
- Script 45 only subset-checks four `never_sealed` IDs; the loader checks all fourteen. Keep the loader pin; make 45 match it.
- No code reads `not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public`.

---

## What the merge did close (do not reopen)

- 0.60 locked; 0.40 floor kept in YAML, protocol, charter, and loader.
- `never_sealed_networks` lists Jinsha, Chattahoochee, and the 12 downloaded IDs; loader refuses a missing ID.
- Loire / Swiss named in the freeze and protocol (charter split still missing — leftover 7).
- BL-015: four stations formula-forced; B1/S2 empirically unflippable; no “any univariate reproduces the paper.”
- Sealed absolute floor 40; 30% is the mix target.
- `DEFAULT_STUDY_FREEZE` → `design_freeze_v9.yaml`; script 45 asserts that id; v1 YAML kept; `DEFAULT_DESIGN_PATH` not retargeted in the files read for this pass.
- Dummy `design_freeze_v9` strings in the two historical tests left alone.
- `evaluate_success` sets `thresholds_locked` from the v9 freeze (but see leftovers 1–2).
- Placements ≥20, Oh & Bartos QR, T4 input paths, T1.4 bound, non-Gaussian fallback, and `best_epoch<50` class-exclusion forbid are in the YAML.

---

## Must-fix leftovers

A second merge that does not do these is not Phase 0 closed.

1. Implement the four-baseline CI rule in `evaluate_success` (and pin it in the loader / script 45). YAML prose is not a lock.
2. Withhold network CIs unless n ≥ 100. Do not let `evaluate_success` pass when the interval is withheld or n < 100.
3. Stop citing the unpatched master-plan Locked gates as the T1–T8 source of truth, or patch that block (add 0.40; sealed floor 40 only; drop “19-network”).
4. Delete “例如 5%” from the protocol and charter. T3(b) operating point is 5% / 0.5°C / 30% / 15 pp, or it is not locked.
5. Split `csdi_or_grin` into two roster entries, or BL the missing model.
6. Remove or alias `intended_locks_after_phase_4` so Phase 4 cannot be read as the lock date.
7. Put the Loire / Swiss exclusion in charter §河怎么分 and pin both IDs in the loader and script 45.
8. Do not count Colorado / Columbia (or other no-overlap sealed rows) toward the sealed 40 until T2 overlap exists.
9. Rewrite freeze `core_question` as a question, not the contribution sentence.
10. Align `validate_catalog` with T2 ≥3 / 3 climates, or make script 45 fail closed on the documented lag until that patch exists.

---

## Acceptable residual risk

- Keeping the `design_freeze_v9` filename while `DEFAULT_DESIGN_PATH` stays v4 and the dummy test strings stay dummy.
- `formal_evidence: false` while T2/T3 numbers are locked floors and sealed outcomes stay unopened.
- 150 as a written target next to the audited 31 / 6 maxima.
- T6 remaining “preferred SEPlains × BFI” **if** leftover 10’s friendlier-zone abuse is accepted as residual rather than a must-fix.
- Johnson 2021 still missing from the protocol body (literature, not a numeric gate).
- Not remapping `network_catalog_v1.yaml` roles in Phase 0.
- Historical `design_freeze_v4` / 134k-run path untouched.
- Not opening sealed temperatures.

---

## What this pass is not

It is not a request to unlock 0.60, rename the freeze, un-burn the 12 rivers, count Loire / Swiss, or call B1/S2 formula identities. Those parent calls stand. Phase 0 is not closed until the must-fix leftovers are in the merged files, not only in this memo.
