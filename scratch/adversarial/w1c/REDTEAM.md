# RED TEAM — W1-C competing protocol pack

Date: 2026-08-26  
Role: Implementer B (adversarial protocol lawyer). Competing pack only. Production tree not edited.  
Location: `scratch/adversarial/w1c/`  
Sealed temperatures were not opened. No new daily values were downloaded. `design_freeze_v4` was not retargeted.

This pack is the next-paper amendment **as it must be written** if the job is to survive a claim-lawyer read. Faithful Implementer A is expected to transcribe the reviewer’s W1-C bullets. Transcription is where the weasels live.

---

## Strictness proof (E5)

The superseded E5 gate was a dam-label classification conjunction: operator AUC ≥ 0.85 and every univariate AUC ≤ 0.65. The v9.1 gate scores true recoverability from known Σ (true conditional risk or true optimal MAE) on node × gap, and requires four things together: operator Spearman ≥ 0.90, best univariate Spearman ≤ 0.70, operator calibration slope in [0.9, 1.1], and Twin E as its own passing cell. That is not a raise of 0.65 to 0.70. 0.65 is classification AUC on `is_dam_like` (7 vs 73), a label the generator currently paints with a marginal high-AR-plus-isolation tattoo that both the operator and the univariates score at 1.0. 0.70 is Spearman on a continuous matched-marginal estimand after Twin E equalizes ACF and donor R², so the features that used to ace the old univariate ceiling are designed to be near chance. The numbers are not subtractable. Extra constraints the old gate did not have: a higher rank floor (0.90 > 0.85) on a continuous, multi-horizon truth rather than a rare binary dam tag; a calibration band with no AUC analogue; and a hard-negative cell the 2×2 never built. A generator retune that pushed dam-label univariate AUC to 0.64 would have *passed* the old gate and still fails Twin E plus calibration. Any sentence that reads “we loosened the univariate ceiling from 0.65 to 0.70,” “Spearman 0.90 is like AUC 0.85,” or “we changed E5 because the six-river pilot missed 0.40” is a claim violation. This pack refuses those sentences.

---

## Weasel words this pack refuses

Do not merge a production protocol that contains these, or close synonyms, without rewriting them to the locked meaning.

| Weasel | Why it is illegal |
| --- | --- |
| 放宽 / relax / loosen / easier gate / 降低门槛 | v9.1 is spec-error correction. T2 floors do not move. E5 is harder. |
| 因为六河没过所以… / after the pilot miss we… | Six-river miss licenses nothing. `six_river_pilot_is_failed_context_not_evidence` stays. |
| univariate ceiling raised 0.65 → 0.70 | Category error. Different estimand. See strictness proof. |
| Spearman 0.90 ≈ AUC 0.85 | Same. |
| 多找到 63 条 / 63 extra rivers / scraped 150 / more inclusive grouping | HUC8 is a tighter unit, not a looser net. 161 − 98 as “extra by loosening” is a claim violation (mandatory attack 4). |
| HUC8 是四站/HUC2 的放宽 | v9 already locked 3 stations. Mixing 4→3 with HUC8 is the scrape-150 trick. |
| 161 条已在手 / 161 ≥ 150 so T2 / T2 is met / inventory 161 | Catalog span ≠ 300 approved days × 8 years. Attrition 25–40%. 161 is not T2 (mandatory attack 5). |
| 合格八年 meaning catalog begin/end | Qualified year is post-QC approved-day count. |
| HUC8-only 166 as honest stock | Exploratory mixed-name table. |
| twins failed / 孪生证明算子不行 / T5 complete / gate_pass false as negative recoverability | Uninformative: wrong y, univariates also AUC 1 (mandatory attack 2). |
| `identifiability_status: separable` as a pass | Operator-half status. Joint gate on the wrong estimand. |
| 调 φ / retune generator / bump constants until 0.65 | φ-hacking to save dam-detection. Twin E is the only allowed design correction (mandatory attack 3). |
| 1% NA-ized is the sentinel rule | Misses Clearwater `13343000` (2/1848 ≈ 0.11%) (mandatory attack 11). |
| 0 °C as sentinel | Ice is real. |
| Loire/Swiss count toward T8 / 10 non-NA sealed | `never_sealed` / not-countable lists stay (mandatory attack 6). |
| remap `*_huc20` / `*_huc31` / `*_huc50` | Token rewrite of burned IDs. |
| rewrite `design_freeze_v4` / change `DEFAULT_DESIGN_PATH` / new `design_freeze_v9.1.yaml` as executable | v9.1 amends the next-paper freeze only (mandatory attack 7). |
| lock the two-tier budget after download / “if too expensive, drop CSDI” | Post-hoc shrink (mandatory attack 8). |
| `csdi_or_grin` one slot | Repeats v5 class-exclusion. |
| 30, 90 **or** 180 / better of 90 and 180 | BL-006 class (mandatory attack 9). |
| 6-river or 12-river network CI / n=5 cluster bootstrap as T2 interval | BL-012 internalized; floor is 100 networks (mandatory attack 10). |
| unfreeze historical / reopen BL-006 / rewrite BL-015 | BL-016 and BL-017 answer “redesign historical freeze?” with NO (mandatory attack 12). |
| `formal_evidence: true` / headline license / reservoir in title | Unchanged false. |
| download the 98-list | Wrong candidate set. |
| empty freeze / lock numbers after seeing attrition | Repeats v8. |
| current twins as T5 done because geometry of Twin A is interior | Geometry ≠ instantiated aliasing. |

---

## Mandatory legal attacks (encoded, not just listed)

1. **T2 not loosened because the 6-river pilot failed.** Protocol Why, What did not change §2, freeze `six_river_pilot_does_not_license_this_change`, BL-016 last sentence, BL-017 last sentence. E5 strictness proof is a dedicated paragraph at the top of the protocol.
2. **`gate_pass: false` is uninformative.** BL-016 question 1 and Update; freeze `current_gate_pass_false_is_uninformative`; protocol What changed §2. Forbidden to call it T5 complete or a negative recoverability result.
3. **Twin E ≠ φ-hacking.** Protocol What changed §4; freeze `do_not_retune_phi_or_isolation_to_save_gate`; BL-016 Twin E paragraph. Equalizing ACF and donor R² instantiates the alias the old design claimed to test. Changing φ to save dam-detection AUC is a different, forbidden act.
4. **HUC8 is not relaxing 4-station/HUC2 to scrape 150.** BL-017 title and paragraph 2; freeze `forbidden_claims`. Pre-empt “161 = 63 extra by loosening.”
5. **161 is not T2.** Catalog dates ≠ 300×8. Attrition 25–40%. Protocol What changed §6; BL-017 question 5.
6. **`never_sealed` not rewritten.** Protocol What changed §8 copies all 14 tokens. Freeze overlay *omits* the list so a merge cannot “fix” tokens. Loire/Swiss still blocked for T8.
7. **`design_freeze_v4` stays the historical executable.** Protocol header and What did not change §1. No `design_freeze_v9.1.yaml`. `design_id` remains `design_freeze_v9`.
8. **Two-tier budget locked before download.** Freeze `model_budget_locked_before_download`, Tier 2 `n_target: 30`, strata, gaps `[30, 90, 180]` all required. Protocol What changed §9.
9. **Horizon shopping remains BL-006.** Tier 2 forbids selecting 90 vs 180 after the envelope; `primary_evidence_forbids` appends the same token already in `forbidden_after_seal`.
10. **Network CI floor 100.** `interval_rule` now names 12-river *and* 6-river pilots. W2 redo: `passed: false`, `purpose: pipeline_verification_not_evidence`.
11. **Ingest QC: any NWIS sentinel ⇒ `rejected_sentinel`.** Clearwater 2/1848 written as the 1% counterexample. 1% remains only for out-of-range NA-ization (`rejected_range`), not for sentinels.
12. **Five-question BL structure.** BL-016 = spec error. BL-017 = grouping defect. Question 4 both NO on historical unfreeze.

---

## Predicted production-doc failures (Implementer A)

These are the failures a faithful transcription of the parent W1-C prompt will ship unless the merger uses this pack.

1. **Missing or weak strictness proof.** Prompt says “document the strictness argument.” Likely one sentence “new gate is harder.” Without an explicit refusal of “0.65→0.70,” reviewers will read a raised univariate ceiling. **Must-fix:** keep the one-paragraph proof; forbid the comparison.
2. **Motivation clause “twins failed, so we change the gate.”** That reads as result-driven. The legal cause is spec error *before* new data, independent of `gate_pass`. **Must-fix:** BL-016 question 3; uninformative, not negative.
3. **Citing `identifiability_status`.** Freeze v9 and the manifest still say `operator_separable_univariates_also_separable`. Production protocol may leave that string live. **Must-fix:** do not cite.
4. **Retune language creep.** “Adjust Twin A AR until univariates drop” or “also retune if Twin E still fails.” Prompt forbids retune; faithful drafts sometimes add a rescue hatch. **Must-fix:** no hatch. Negative result is allowed.
5. **161 sold as T2.** The reviewer’s own prose says “T2 的 150 条目标就已经达到了（161 ≥ 150）.” Implementer A may quote that. This pack **overrides the reviewer** on that sentence. Catalog ≠ qualified years. **Must-fix:** 161 labelled catalog-only everywhere, including feasibility docs written in parallel by W1-A.
6. **“63 extra” / “raised from 98 to 161.”** Even without the word “loosen,” a delta invites the scrape reading. **Must-fix:** name×HUC2 is a false ceiling; HUC8 is a different unit; 98 remains as contrast audit, not a baseline we beat.
7. **Mixing 4→3 with HUC8.** v9 `stations_per_network_min: 3` plus HUC8 in one paragraph becomes “we relaxed to 3 stations and HUC8 to reach 150.” **Must-fix:** separate sentences.
8. **Mixing v2 HUC8-only 166 with v3 ~161.** **Must-fix:** 166 exploratory, excluded.
9. **`never_sealed` retokenized** when pointing at `network_catalog_v3_huc8.yaml` (padded HUC2 IDs). Script 51 already wants to drop burned IDs. **Must-fix:** overlay does not rewrite the 14 strings; validator must still see them.
10. **Loire/Swiss as the 10 non-NA sealed.** Prompt says they are not countable; a split-lock writer will still need 10 seats and may pad. **Must-fix:** T8 block unchanged; European daily is W6, not W1.
11. **New freeze file `design_freeze_v9.1.yaml`** or `design_id: design_freeze_v9.1`, or `DEFAULT_STUDY_FREEZE` retarget. Prompt says keep `design_id: design_freeze_v9`. **Must-fix:** amendment key only.
12. **T2 floors copied as “still 0.60” in prose but YAML edited.** Watch `out_of_network_spearman_min` and `network_bootstrap_lower_bound_min`. This overlay does not include those keys as changes.
13. **Tier 2 sample rule underspecified.** Prompt says n≈30, strata, gaps 30/90/180. Faithful YAML may say `tier_2: deep_models_on_subset` with no n, no strata, no lock-before-download. Then the subset is chosen after seeing which rivers score. **Must-fix:** n 28–32, three strata, SHA lock, all three gaps.
14. **`csdi_or_grin` left as OR.** v9 leftover. **Must-fix:** both names on Tier 2.
15. **Interval rule still only mentions the 12-river pilot.** W2 is 6 rivers. `evaluate_success` today can pass when n<5 because a non-tested interval counts as pass (`docs/_adversarial/v9_protocol_redteam.md` leftover 2). This pack writes the rule; production must still patch `evaluate_success`. Protocol-only merge will leave the hole executable.
16. **Ingest QC copied as the reviewer’s 1% list without the any-sentinel override.** Prompt for W1-C says “note the Clearwater hole.” A short note without changing the rule leaves `13343000` accepted. **Must-fix:** sentinel rule is primary; 1% is `rejected_range` only.
17. **QC as whole-river drop.** Clearwater was dropped as a network by MAE>50. Station-level verdicts are the attrition table. **Must-fix:** station rows.
18. **BL five-question question 4 answered YES.** That would unfreeze v4. **Must-fix:** NO, both BLs, same sentence as BL-015 q4.
19. **Rewriting BL-015** while appending 016/017. Prompt says do not. **Must-fix:** append only.
20. **W2 6-river Spearman CI in the protocol as a “preview of T2.”** **Must-fix:** n=6 cannot report network CIs; `passed: false` by construction for confirmatory eligibility.
21. **Hold-out twin family not locked.** Old leftover: design suite = scored suite. New Spearman 0.90 on the same 14 graphs is still an in-sample identity. This pack requires a hold-out family locked before scoring. Faithful A may omit it.
22. **Twin D clone ignored.** Not W1-C’s to recode, but a protocol that says “2×2 plus Twin E” without “D is not a cell until de-cloned” revives four labels / three designs.
23. **Charter still leading with “独立河网目标 ≥150” as if 161 satisfied it.** Validator may not read the amendment. **Must-fix:** script 45 must require v9.1 file + BL-016/017 + E5 keys + never_sealed 14, and must not treat catalog 161 as `passed`.
24. **`provisional_success_criterion.intended_locks_after_phase_4` left as a second calendar** that could reopen T2 after seeing download attrition. v9 already locked; v9.1 must not revive “lock later.”

---

## What this pack does not claim

- It does not compute the exact HUC8 count (W1-A). 161 is the reviewer’s truncated number, labelled approximate.
- It does not implement Twin E or ingest QC (W1-B / later). It locks the rules those implementations must obey.
- It does not open sealed temperatures or download NWIS.
- It does not declare T2, T5, or T7 passed.
- It does not treat the reviewer’s sentence “161 ≥ 150 so T2 is in hand” as binding. That sentence is the hole BL-017 exists to close.

---

## Files

| File | Role |
| --- | --- |
| `protocol_change_v9_to_v9.1.md` | Chinese amendment, v8→v9 tone |
| `BL-016.md` | Spec error, five questions |
| `BL-017.md` | Grouping defect, five questions |
| `freeze_patch.yaml` | Additive keys only; never_sealed omitted on purpose |
| `REDTEAM.md` | This memo |

Merge instruction: copy protocol to `docs/`, append BLs to `paper/boundary_ledger.md` without editing BL-015, overlay YAML keys onto `configs/design_freeze_v9.yaml` without changing `design_id` or T2 floors, then make script 45 require the new files. Do not merge weasels. Do not retarget v4.
