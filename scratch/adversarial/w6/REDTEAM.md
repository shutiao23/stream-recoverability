# RED TEAM: W6 Europe T8 source weasels

Date: 2026-08-26
Role: Implementer B (adversarial). Attack production W6 Europe only. Not a license to retune, download the USGS 98 name×HUC2 list, open Loire/Swiss/sealed temperatures, or retarget `design_freeze_v4`.
Scope: `scripts/71_w6_europe_source_audit.py`, `scripts/63_uk_ea_temperature_catalog.py`, `scripts/65_uk_ea_daily_from_readings.py`, `src/stream_recoverability/data/hubeau_temperature.py`, `src/stream_recoverability/data/uk_ea_temperature.py`, `results/framework/public_catalog/w6_*`, `results/framework/public_rivers_europe/uk_ea_*`.
Correct scratch path: `scratch/adversarial/w6/` (this pack). Production `src/`, freeze YAML, and `results/` were not edited.

T8 (locked): 3 stations × 8 overlapping **daily** years under provider QC, concurrent enough for the 5×365-day floor. Catalog span, `dateOpened`, instantaneous Hub'Eau chronique, name clusters, and spatial catalog clusters are not T8. Europe complete_enough is a T8 **candidate increment**. T2 still needs n≥100 cluster bootstrap. 59 (8yr) / 67 (6yr failure_closure) NA open networks remain below that floor.

---

## Verdict

Production W6 is an honest **zero** on Hub'Eau Correcte and UK EA `n_complete_enough`. That honesty is one flag-flip from a lie. The live hole is name-only clustering that found Derwent, downloaded it, and stopped while 1948/1964 UK rows have blank `riverName` and complete lat/lon. The predicted merge weasels are: bulk-download Sandre code 4 (`Non qualifié`) and count it as T8; treat `dateOpened` as overlapping daily years; pad with Loire, Swiss FOEN values, or the USGS 98-list; and sell `n_complete_enough>0` as a T2 pass or a `tested` network CI.

Flipping `countable_toward_t8` / `hubeau_correcte_t8_usable` / `passed` without 3×8 daily years is a T8/T2 lie. Tests: `test_flag_only_w6_done_pr_is_rejected`.

---

## 1. Hub'Eau Correcte=0 ignored, then code 4 bulk-downloaded and counted as T8

**Naive.** Live temperature chronique is 100% code 4 `Non qualifié` on `06213500` (10472 instantaneous points, 14.95 yr span), `06175400` (201121, 12.38 yr), `06151000` (12.89 yr), `05223000`. Filter `code_qualification=1` returns 0. W6 audit already writes `hubeau_n_sites_with_sandre_correcte_observations: 0`. The naive patch is: drop the Correcte filter, bulk-download code 4, relabel `q=4` as Correcte, or promote instantaneous first/last timestamps to 8-year daily networks.

**Required.** Sandre 1 is `Correcte`. Codes 2–4 are not T8-eligible. Instantaneous span years are not overlapping daily years. `hubeau_correcte_t8_usable` stays false while Correcte=0. `countable_toward_t8` stays false unless 3 stations share ≥8 overlapping **daily** years and ≥1825 concurrent days. Scratch: `w6_contract.t8_countable(..., code_qualification="4")` and `instantaneous_span_years=...` both return false.

**Flag-only weasel.** Set `hubeau_unqualified_code_4_accepted: false` and `hubeau_correcte_t8_usable: true` (or `countable_toward_t8: true`) while the station audit is still 0 Correcte. Tests: `test_hubeau_code4_live_sites_have_zero_correcte`, `test_instantaneous_span_is_not_eight_daily_years`, `test_relabeling_code4_as_correcte_is_not_t8`, `test_hubeau_correcte_t8_usable_false_while_audit_is_zero`.

---

## 2. UK EA `dateOpened` or catalog span treated as overlapping daily years

**Naive.** Catalog: 1964 stations, lat/lon complete, river names on 16 rows (1948 blank). Live API `riverName` is also mostly missing. Every row has `dateOpened`. 1053 stations have `dateOpened` ≥8 years before 2026-08-26. Treating that elapsed time, or a catalog first/last, as overlapping daily years invents Europe years. `uk_ea_daily_manifest.json` `n_complete_enough: 0` is the honest download result (Derwent: 2 stations with daily values, 0 concurrent years, `complete_enough=False`).

**Required.** `dateOpened` is metadata. `has_public_daily_span` is false for all 1964 rows. Overlapping daily years come only from dated daily (or resampled-and-densely-observed) values with 3 concurrent stations. `europe_daily_years_invented` stays false. Scratch: `t8_countable(..., date_opened_years=fake)` is false even when `fake>8`.

**Flag-only weasel.** Leave `europe_daily_years_invented: false` and write `n_complete_enough: 1` from `dateOpened`. Tests: `test_uk_ea_catalog_is_metadata_not_daily_years`, `test_date_opened_years_are_not_overlapping_daily_years`, `test_derwent_download_is_not_complete_enough`, `test_invented_europe_daily_years_fail_contract`.

---

## 3. Name-only clustering that pretends 1964 stations yield 1 network, then stops

**Naive.** Script 63 groups non-blank `riverName` and finds one 3-station cluster (River Derwent). Script 65 downloads that one river and stops. 1948 blank names never enter a cluster. Production `n_rivers_attempted: 1`. Calling that exhaustion of the 1964-station catalog is the weasel. If production only re-runs Derwent, W6 still has 0 Europe `complete_enough`.

**Required.** Spatial clustering on lat/lon with a 50 km complete-linkage cap (analog of the HUC8 max-pair diagnostic) is the next **catalog** move. Blank-name stations near Derwent exist on disk within 50 km. Scratch `spatial_clusters_50km` recovers an unnamed triplet that `name_clusters` drops. A 3-station name group on a 120 km baseline is **not** a 50 km spatial network.

Catalog clusters still must not be counted as T8. Spatial output sets `countable_toward_t8: false` and `catalog_cluster_only: true`. This pack does not download the 1964 reading archive.

**Flag-only weasel.** `n_name_clusters_3plus: 1` sold as 1 T8 network, or “W6 done” while spatial clustering was never attempted. Tests: `test_production_name_clustering_found_only_derwent_then_stopped`, `test_toy_spatial_50km_recovers_blank_name_triplet_name_clustering_drops`, `test_name_cluster_wider_than_50km_is_not_a_spatial_network`, `test_spatial_catalog_cluster_still_not_t8`. Honest production still ships `name_only_clustering_stopped_after_derwent`.

---

## 4. Padding T8 with Loire, Swiss FOEN opened values, or the USGS 98-list

**Naive.** Europe is 0 complete. Pad with Loire last-check temperatures, Swiss FOEN `data_1day_mean` values now that GraphQL is public, or the retired USGS name×HUC2 98-list so T8 looks non-zero. Freeze already says `loire_swiss_still_not_countable_for_t8: true` and `do_not_download_name_huc2_98_list: true`. FOEN GraphQL reachable is not opened outcomes (`temperature_values_requested: false`, `swiss_countable_toward_t8: false`).

**Required.** Loire stays last-check and unopened. Swiss stays uncountable until a protocol amendment **before** values are opened. USGS 98-list is not a Europe (or T8) rescue. `loire_downloaded: false`. `design_freeze_v4` stays the historical executable (`DEFAULT_DESIGN_PATH`, `EXECUTABLE_DESIGN_VERSION`). This pack did not open Loire/Swiss/sealed temperatures and did not download the 98-list.

**Flag-only weasel.** `foen_public_graphql_reachable: true` rewritten as Swiss countable; `loire_downloaded: false` while Loire values are on disk; 98-list harvested into `n_europe_complete_enough_added`. Tests: `test_loire_swiss_98_list_cannot_pad_t8`, `test_design_freeze_v4_was_not_retargeted`.

---

## 5. Calling `n_complete_enough>0` a T2 pass or reporting network CI at n≪100

**Naive.** One Europe complete_enough network, or a flag that claims it, becomes `passed: true`, `inference_status: tested`, or a 60-network cluster-bootstrap CI. Freeze: `n_networks_min: 100`, `withhold_network_ci_if_n_lt_100: true`. Open NA stock is 59 complete_enough at 8 qualified years and 67 at 6-year failure_closure (47 development + 20 validation). 59+1 and 67+1 are still below 100.

**Required.** Europe adds T8 **candidates**. T2 still needs n≥100 cluster bootstrap after ingest QC. W6 `passed: false`, `t2_passed: false`, `network_interval.inference_status: withheld_n_lt_100_network_interval`. Never write `tested`. Scratch: `europe_adds_t8_not_t2(1)["t2_passed"] is False`.

**Flag-only weasel.** `n_complete_enough: 1` + `passed: true` + `inference_status: tested` with Derwent still incomplete and Hub'Eau still 0 Correcte. Tests: `test_europe_complete_enough_is_not_a_t2_pass`, `test_passed_true_or_tested_ci_fails_w6_contract`, `test_flag_only_w6_done_pr_is_rejected`.

---

## If production only sets the flags to “W6 done”

Still ships:

| # | Hole | Why the flag is not a fix |
| --- | --- | --- |
| 1 | Code 4 as T8 | Correcte count is still 0. Relabeling q=4, or counting 10472/201121 instantaneous points as 8-year daily, is the lie. |
| 2 | dateOpened as daily years | Catalog still has `has_public_daily_span: false`. Derwent overlap is still 2 stations / 0 years. |
| 3 | Name-only then stop | 1948 blank names and lat/lon were never clustered at 50 km. Derwent re-run cannot create Europe complete_enough. |
| 4 | Loire / Swiss / 98-list pad | Freeze still forbids counting them. GraphQL reachable ≠ values opened. |
| 5 | T2 pass / `tested` CI | 59/67 ≪ 100 even after a real Europe T8 candidate. |

Holes 1–5 **will still ship** under a flag-only patch. That is the merge blocker.

---

## Naive vs required (one line each)

| | Naive | Required (this pack) |
| --- | --- | --- |
| Hub'Eau QC | Bulk-download code 4; relabel as Correcte | Correcte=1 only; 0 sites ⇒ `hubeau_correcte_t8_usable: false` |
| Hub'Eau years | Instantaneous first/last as 8 daily years | Concurrent daily density; span years are not T8 |
| UK years | `dateOpened` or catalog span | Dated daily overlap; `europe_daily_years_invented: false` |
| UK clustering | 1964 → 1 Derwent name cluster, stop | 50 km spatial catalog pass; still not T8 |
| Padding | Loire, Swiss values, USGS 98-list | All forbidden; FOEN reachable is not countable |
| T2 | `n_complete_enough>0` ⇒ pass / `tested` CI | n≥100; 59/67 remain below; `passed: false` |

---

## Merge instructions for parent

1. **Reject a patch that only flips W6 flags.** Required keys: `scratch/adversarial/w6/manifest_contract.json`. `countable_toward_t8` false unless 3 stations × 8 overlapping daily years. `hubeau_correcte_t8_usable: false`. `europe_daily_years_invented: false`. `loire_downloaded: false`. Production's combined W6 audit currently **omits** `hubeau_correcte_t8_usable` and `europe_daily_years_invented`; filling them as `true` is the flag-only lie. Missing must be read as false.
2. Do not bulk-download Hub'Eau code 4 to “fill” Correcte=0. Do not relabel `Non qualifié` as `Correcte`. Instantaneous spans (`06213500` 10472, `06175400` 201121) are not T8.
3. Do not treat UK EA `dateOpened` as overlapping daily years. Derwent remains not `complete_enough`.
4. Name clustering is exhausted at Derwent. Next **catalog** move is 50 km lat/lon clustering. Do not count those clusters as T8. Do not claim W6 done because Derwent was re-run.
5. Do not open Loire or Swiss temperatures. Do not count FOEN GraphQL reachability. Do not download the USGS 98 name×HUC2 list. Do not retarget `design_freeze_v4`.
6. Do not write `passed: true` or `inference_status: tested`. Europe T8 candidates do not license T2. 59 (8yr) / 67 (6yr) stay below n≥100.
7. Port tests from `scratch/adversarial/w6/test_w6_europe_weasels.py`. Keep them failing a flag-only “W6 done” PR.

---

## Pack layout

| Path | What |
| --- | --- |
| `scratch/adversarial/w6/REDTEAM.md` | This memo |
| `scratch/adversarial/w6/manifest_contract.json` | Required W6 keys |
| `scratch/adversarial/w6/w6_contract.py` | T8/T2 contract; flag-only hole detector |
| `scratch/adversarial/w6/spatial_cluster.py` | Toy 50 km complete-linkage helper (no 1964 download) |
| `scratch/adversarial/w6/test_w6_europe_weasels.py` | Weasels 1–5, flag-only, freeze v4, 59/67 |
| `scratch/adversarial/w6/demo/flag_only_w6_done.json` | Lying “W6 done” PR; tests reject it |

## Scratch run

```bash
PYTHONPATH=src python scratch/adversarial/w6/spatial_cluster.py
python -m pytest scratch/adversarial/w6/test_w6_europe_weasels.py -q
```

Sealed temperatures were not opened. Loire was not queried. USGS 98-list was not downloaded. Twin generator was not edited. Freeze YAML was not retargeted.
