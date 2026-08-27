# RED TEAM: W7 T2 confirmatory weasels

Date: 2026-08-26
Role: Implementer B (adversarial). Attack a W7 first-layer T2 slice sold as confirmatory. Not a license to retune Twin E / φ, download the USGS 98 name×HUC2 list, open Loire/Swiss/sealed HUC8 temperatures, or retarget `design_freeze_v4`.
Scope: `results/framework/t2_recovery_benchmark_v1/workload_manifest.json`, `scripts/74_prepare_t2_recovery_benchmark.py`, `scripts/79_run_t2_chunk.py`, `src/stream_recoverability/experiments/t2_recovery_benchmark.py`, `src/stream_recoverability/analysis/hierarchical_confirmation.py` (`evaluate_success`), W6 Europe audits, Hub'Eau Sandre QC, UK EA hydrometric overlap, M/H blocked cells, Twin E freeze text.
Correct scratch path: `scratch/adversarial/w7/` (this pack). Production `src/`, freeze YAML, and `results/` were not edited.

T2 (locked): cluster-bootstrap network CI and confirmatory `evaluate_success` require n≥100 independent networks after ingest QC. Open-role stock is **67** at 6-year `failure_closure6` (47 development + 20 validation) and **59** at 8 qualified years (43+16). Both stay `withheld_n_lt_100_network_interval`. `go_no_go: NO_GO_T2_PRIMARY_EVIDENCE`. W7 first layer is cheap models on **B / D / B_union_D** only. M/H cells stay blocked. Europe complete_enough is still 0. Incremental R² vs `donor_r2_only` below 0.05 is W8 **retitle**, not retune.

---

## Verdict

Production W7 is an honest **NO_GO** at n=67. That honesty is one flag-flip from a confirmatory T2 claim. The predicted merge weasels are: sell 67 (or 59) as `tested`; add W6 catalog clusters or the 5.91-year UK EA overlap to n; relabel Hub'Eau code 4 as Correcte; write `passed: true` while `evaluate_success` still fails; open sealed HUC8 / FOEN / Loire to pad n; relabel M/H-blocked cells as executable; retune the operator or φ because incremental R² vs donor R² is below 0.05.

Flipping `passed` / `go_no_go` / `inference_status` without n≥100 is a T2 lie. Tests: `test_flag_only_t2_done_pr_is_rejected`.

---

## 1. Selling n=67 (or n=59 8-year) as confirmatory T2 / reporting network CI as `tested`

**Naive.** Workload already has 67 open-role networks and frozen geometry. Write `passed: true`, `confirmatory_eligible: true`, `go_no_go: GO_T2_PRIMARY_EVIDENCE`, or `inference_status: tested` with a cluster-bootstrap interval. Quote 59 eight-year networks as if the qualified-year rule were the confirmatory floor. Freeze: `n_networks_min: 100`, `withhold_network_ci_if_n_lt_100: true`. Live `evaluate_success` on a 67-network panel still withholds.

**Required.** Status remains `withheld_n_lt_100_network_interval`. `ci_lower` / `ci_upper` stay null. `passed: false`. `evaluate_success.passed: false`. `evaluate_success.n_networks_min: 100`. `go_no_go: NO_GO_T2_PRIMARY_EVIDENCE`. Purpose is `development_slice_not_evidence` (or `pipeline_verification_not_evidence`). Scratch: `network_ci_status(67) == withheld_n_lt_100_network_interval`.

**Flag-only weasel.** `n_networks: 67` plus `inference_status: tested`. Tests: `test_n_67_and_n_59_cannot_be_confirmatory_t2`, `test_tested_ci_at_n_lt_100_fails_contract`.

---

## 2. Counting W6 Europe catalog clusters or 5.91-year UK EA overlap as T8/T2 n increment

**Naive.** W6 hydrometric spatial download found 6 clusters / 85 catalog 50 km groups. Best concurrent overlap is **5.91 years** on `uk_ea_s50_002` (4 stations, 2139 days with min stations — that clears 5×365 days and still misses 8 overlapping daily years). Add 6 or 85 to 67 and call it T8 or T2 n. 67+85 looks like 152 ≥ 100.

**Required.** Catalog clusters are not T8. 5.91 years is not 8. `n_complete_enough: 0`. `europe_complete_enough_used: false`. `t8_or_t2_n_increment: 0`. Concurrent-day floor without the year floor is still a miss. Scratch: `europe_does_not_increment_t2(n_catalog_clusters=85, overlap_years=5.91)`.

**Flag-only weasel.** `n_europe_complete_enough_added: 85` while production Europe is 0. Tests: `test_europe_catalog_clusters_and_5_91_overlap_are_not_t8_or_t2`.

---

## 3. Counting Hub'Eau code 4 Non qualifié as Correcte/T8

**Naive.** Live temperature chronique is 100% code 4 on `06213500`, `06175400`, `06151000`, `05223000`. Filter `code_qualification=1` returns 0. Relabel q=4 as Correcte, or count instantaneous spans as 8-year daily networks, then add those sites to T8/T2 n.

**Required.** Sandre 1 is Correcte. Codes 2–4 are not T8-eligible. `hubeau_correcte_t8_usable: false` while Correcte=0. Scratch: `t8_countable(..., code_qualification="4")` is false even at 3×8 daily years.

**Flag-only weasel.** `hubeau_correcte_t8_usable: true` with audit still 0 Correcte. Tests: `test_hubeau_code4_is_not_correcte_or_t8`.

---

## 4. Flag-only `passed: true` while `evaluate_success` still fails

**Naive.** Slice writer sets top-level `passed: true` (or copies a fake `evaluate_success.passed: true`) without calling `evaluate_success`. Live confirmatory rule still fails: n=67 < 100, interval withheld, `confirmatory_eligible: false`.

**Required.** Top-level `passed` cannot be true unless live `evaluate_success.passed` is true, which cannot happen at n<100. A PR that only flips the flag still ships a failed confirmatory gate. Tests: `test_passed_true_while_evaluate_success_still_fails`, `test_flag_only_t2_done_pr_is_rejected`.

---

## 5. Opening sealed HUC8 / FOEN / Loire to pad n

**Naive.** Open-role 67 is short of 100. Read sealed-role HUC8 outcomes (example `huc8_03050201`), request FOEN `data_1day_mean` values because GraphQL is reachable, or download Loire last-check temperatures. Add them to scored n. Freeze forbids Loire/Swiss as T8; sealed temperatures stay unread during development; never-sealed 14 tokens stay out.

**Required.** `sealed_outcomes_opened: false`. `sealed_input_roots_allowed: []`. `loire_downloaded: false`. `swiss_countable_toward_t8: false`. `foen_temperature_values_requested: false`. GraphQL reachable is not opened outcomes. USGS 98-list is not a rescue. Workload open ids are disjoint from sealed catalog roles. Scratch: `n_cannot_reach_floor_by_padding(sealed_huc8=40, loire=1, swiss=1)`.

**Flag-only weasel.** `foen_public_graphql_reachable: true` rewritten as Swiss countable; sealed HUC8 ids mixed into `n_networks`. Tests: `test_sealed_huc8_foen_loire_cannot_pad_n`.

---

## 6. Relabeling M/H-blocked cells as executable to inflate the grid

**Naive.** Workload first layer already lists `B_union_D_union_M` and `B_union_D_union_M_union_H`. Auxiliary is incomplete (13 of 67 terminal). Rewrite `structural_not_applicable|structural_unimplemented_no_meteorology_or_hydraulics_adapter` (403424 items) as `executable` so `n_executable` jumps from 294460 to 697884, then claim the W7 grid is complete.

**Required.** W7 first layer is **B / D / B_union_D** only. M/H stay blocked until meteorology and hydraulics are bound on all 67 networks. Semantics remain `blocked_until_meteorology_M_is_bound` / `blocked_until_M_and_hydraulics_H_are_bound`. Geometry `blocked_cells` keep `meteorology_M_information_cells_unbound` and `hydraulics_H_information_cells_unbound`. `mh_blocked_cells_relabeled_executable: false`.

**Flag-only weasel.** `n_executable: 697884` with `meteorology_M: false`. Tests: `test_mh_blocked_cells_cannot_be_relabeled_executable`.

---

## 7. Retuning operator / φ because incremental R² vs `donor_r2` < 0.05

**Naive.** Nested increment after `donor_r2_only` comes in below 0.05 (or ≤0). Change φ, isolation, Twin E lag, or the Schur operator until the step clears 0.05. Freeze failure_closure: if the operator is no better than donor R², **retitle** to predictability; do not retune. Twin E is a design correction already locked; `do_not_retune_phi_or_isolation_to_save_gate: true`.

**Required.** Record the increment honestly. If < 0.05, W8 action is `retitle_to_predictability`. `operator_retuned_because_incremental_r2_lt_005: false`. `twin_e_retuned: false`. Scratch: `operator_or_phi_retune_licensed(0.02) is False` even though `w8_failure_closure_action(0.02) == "retitle_to_predictability"`.

**Flag-only weasel.** `w8_failure_closure_action: retune_operator_and_phi` with incremental R² 0.02. Tests: `test_incremental_r2_below_0_05_is_w8_retitle_not_retune`.

---

## If production only sets the flags to “T2 done”

Still ships:

| # | Hole | Why the flag is not a fix |
| --- | --- | --- |
| 1 | n=67/59 as T2 / `tested` CI | Floor is n≥100. Live `evaluate_success` still withholds. |
| 2 | Europe 5.91 / 85 clusters as n | `n_complete_enough` is still 0. 5.91 < 8. |
| 3 | Code 4 as Correcte | Correcte count is still 0. |
| 4 | `passed: true` | `evaluate_success.passed` remains false at n<100. |
| 5 | Sealed / FOEN / Loire pad | Freeze still forbids counting them. GraphQL reachable ≠ values opened. |
| 6 | M/H executable | 13/67 auxiliary terminal; adapters still unimplemented. |
| 7 | Retune for ΔR² < 0.05 | Failure_closure is retitle, not φ-hacking. |

Holes 1–7 **will still ship** under a flag-only patch. That is the merge blocker.

---

## Naive vs required (one line each)

| | Naive | Required (this pack) |
| --- | --- | --- |
| n=67 / n=59 | Confirmatory T2; `tested` CI | `withheld_n_lt_100_network_interval`; `passed: false` |
| Europe | 85 clusters or 5.91 years → n++ | Catalog/5.91 add 0; complete_enough stays 0 |
| Hub'Eau | Code 4 as Correcte/T8 | Correcte=1 only; 0 sites ⇒ unusable |
| `passed` | Flip the flag | Live `evaluate_success` must pass; it cannot at n<100 |
| Padding | Sealed HUC8, FOEN values, Loire | All forbidden; reachable ≠ opened |
| Grid | Relabel M/H blocked as executable | B/D/B_union_D only; 403424 stay blocked |
| ΔR² < 0.05 | Retune operator / Twin E / φ | W8 retitle to predictability |

---

## Merge instructions for parent

1. **Reject a patch that only flips W7 T2 flags.** Required keys: `scratch/adversarial/w7/manifest_contract.json`. `passed: false`. `go_no_go: NO_GO_T2_PRIMARY_EVIDENCE`. `network_interval.inference_status: withheld_n_lt_100_network_interval`. `evaluate_success.passed: false`. `evaluate_success.n_networks_min: 100`.
2. Do not sell n=67 or n=59 as confirmatory T2. Do not write `tested`.
3. Do not count W6 Europe catalog clusters (85 at 50 km, 6 hydrometric) or the 5.91-year UK EA overlap as T8 or T2 n.
4. Do not relabel Hub'Eau code 4 `Non qualifié` as Correcte. Instantaneous spans are not T8.
5. Do not set `passed: true` while live `evaluate_success` fails.
6. Do not open sealed HUC8, FOEN values, or Loire. Do not download the USGS 98 name×HUC2 list. Do not retarget `design_freeze_v4`.
7. Do not relabel M/H-blocked cells as executable. W7 first layer is B / D / B_union_D.
8. If incremental R² vs `donor_r2_only` is < 0.05, W8 is retitle, not retune. Do not retune Twin E / φ.
9. Port tests from `scratch/adversarial/w7/test_w7_t2_weasels.py`. Keep them failing a flag-only “T2 done” PR. If a production slice appears under `results/framework/t2_recovery_benchmark_v1/w7_open_role_bd_slice/`, `test_production_w7_slice_if_present_cannot_claim_t2` must still pass.

---

## Pack layout

| Path | What |
| --- | --- |
| `scratch/adversarial/w7/REDTEAM.md` | This memo |
| `scratch/adversarial/w7/manifest_contract.json` | Required W7 T2 keys |
| `scratch/adversarial/w7/w7_contract.py` | T2/T8/M/H/W8 contract; flag-only hole detector |
| `scratch/adversarial/w7/test_w7_t2_weasels.py` | Weasels 1–7, flag-only, freeze v4, 59/67 |
| `scratch/adversarial/w7/demo/flag_only_t2_done.json` | Lying “T2 done” PR; tests reject it |

## Scratch run

```bash
python -m pytest scratch/adversarial/w7/test_w7_t2_weasels.py -q
```

Sealed temperatures were not opened. Loire was not queried. USGS 98-list was not downloaded. Twin E / φ were not retuned. Freeze YAML was not retargeted. Production files were not edited.
