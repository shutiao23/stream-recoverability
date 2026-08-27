# Red team: v9 Hub'Eau year-chunk + T7 lock + T5 BFI (second pass)

Date: 2026-08-26
Role: Red adversarial reviewer. No worktrees. No implementation.
Targets:
- `src/stream_recoverability/data/hubeau_temperature.py`
- `scripts/62_hubeau_daily_from_chronique.py`
- `tests/test_hubeau_temperature.py`
- `src/stream_recoverability/analysis/public_confirmatory_lock.py`
- `scripts/66_propose_public_confirmatory_lock.py`
- `scripts/64_matched_regulation.py` (BFI join)
- `docs/v9_redesign_master_plan.md` T8 / last-check / do-not-invent-Europe-years
Status: not a result. Not a license to count Europe toward T8 or to lock T7.

Live Hub'Eau check (station `06121500`, 2026-08-26): `count` is the collection total (80563). `page=1&size=20000` returns 20000 rows and a `next` URL with `page=2&size=20000`. That `next` is HTTP 400 `ValidatePageDepth` (`page * size` cannot exceed 20000). A 2009 calendar year window returns `count=8760` with no `next`.

---

## MUST-FIX

1. **The named year-chunk is not implemented.** `hubeau_chronique_daily` still opens the *full* first/last chronique span as one window (`hubeau_temperature.py` `hubeau_chronique_rows`), then binary-bisects only if `count > 20000`. The cache suffix `_daily_yearchunk.csv` and master-plan line “Hub'Eau year-chunk is implemented” are overclaim. The first request for `06121500` is a 16 MB 20k-row page that is then discarded. Stations in `hubeau_non_loire_chronicle_spans.csv` already failed the cheap `size=1` span probe with connection reset (`06100900`, `06059500`, …). Calendar-year windows (empirically <20k for this station) must be the *first* fetch, not a leftover name. Do not invent years to skip the re-download.

2. **Stale page-walk artifacts are still the Europe “daily” product.** There is no `*_daily_yearchunk.csv` on disk. `data/public_rivers/hubeau/06100900_daily.csv` and `06059500_daily.csv` are the old ~1–2 year truncated walks. `results/framework/public_rivers_europe/overlap.csv` still reports Rhône 641 days / 1 station and Saône 242 days / 1 station. Tombstone or delete those `_daily.csv` files and the truncated wides (`hubeau_le_rhone_daily_wide.csv`, `hubeau_la_saone_daily_wide.csv`) before any re-run is treated as the year-chunk result. Do not cite 641/242 days as Europe daily history.

3. **Empty-cache guard is header-only.** `hubeau_chronique_daily` unlinks an empty CSV and does not write empty success caches. A *non-empty truncated* `_daily_yearchunk.csv` is trusted forever (early return, no span-length check, no `next` check, no `len(data)==size` check). Tests only cover a header-only file (`tests/test_hubeau_temperature.py` `test_empty_yearchunk_cache_is_not_treated_as_data`). If a crash or a full 20k page is saved as “done,” later runs will not refetch. Refuse cache hits that do not cover the public first/last dates, or that equal a full page without a split.

4. **Full page is treated as complete whenever `count <= 20000` (or `count` is missing).** `int(document.get("count") or 0)` becomes 0 if `count` is absent, so a truncated page is returned and cached. The live API *does* send a total `count` and a `next` link when more rows exist. The client ignores `next`. That is correct today only while nobody follows `next` (page 2 × size 20000 is 400). Defense: if `next` is present or `len(data) == HUBEAU_PAGE_SIZE`, split the date window; never follow `next` at `size=20000`.

5. **Library daily fetch does not refuse Loire / last-check IDs.** `cluster_hubeau_rivers(..., exclude_loire=True)` and script 62’s `last_check_site_ids()` filter are caller conventions. `hubeau_chronique_daily` / `hubeau_chronique_rows` / `hubeau_chronicle_span` will download any `site_id`, including catalog Loire IDs `04000100`–`04134700`. Docstring “must not be passed in” is not a gate. Tests assert `"Loire" in inspect.getsource(...)`, which a comment satisfies. Deny last-check IDs inside the fetch function.

6. **T7 can lock a sealed list that drops the 10 non-NA seats.** `propose_sealed_networks` checks `len(eligible) >= 40` and `len(non_na) >= 10` on the *pool*, then sets `sealed_network_ids = eligible[-floor:]`. If Europe is first in `candidates`, the last 40 can be all North America while `enough_to_lock` is True. Script 66 currently appends NA then Europe, so the slice *happens* to keep Europe — that is order luck, not a contract. Tests (`test_lock_records_ids_without_opening_temps`) never assert that the sealed IDs themselves contain ≥10 non-NA. Require the *sealed set* to contain ≥40 and ≥10 non-NA, independent of input order.

7. **`complete_enough` is a Python truthiness test, not a boolean parse.** `bool(row.get("complete_enough"))` and script 66 `bool(getattr(row, "complete_enough", False))` treat `nan` as True (`bool(float("nan")) is True`) and the string `"False"` as True. Name-cluster rows with a blank `complete_enough` cell would become lock-eligible. Parse with an explicit True/False allow-list (and require overlap years / station count if those columns exist). Do not lock on name clusters.

8. **Missing/`unknown` continent counts as non-NA.** Default continent is `"unknown"`; anything other than `{north_america, na, ""}` increments `non_north_america_n`. `"North America"` (wrong case) would also count toward the 10. The freeze list `not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public` (`loire_mainstem`, `swiss_aar_rhine`) is never read. Name tokens still catch `loire`/`swiss`; that is not the freeze field.

9. **Lock floors are not clamped.** `int(split.get("sealed_min_networks") or 40)` will honor a freeze edit of `30` (the leftover “30–40” in the master-plan T7 sentence). `scripts/45_validate_research_charter.py` and `load_study_freeze` do not require `sealed_min_networks >= 40` or `sealed_min_outside_north_america >= 10`. Clamp in the lock function: never lock below 40+10 even if the YAML shrinks.

10. **Default Europe harvest cannot supply the 10 non-NA seats.** Script 62 `--max-rivers` default is 8. UK EA catalog has one 3-station name cluster (Derwent), `countable_public_daily: False`, and no `uk_ea_overlap.csv` yet. 8 Hub'Eau + 1 Derwent = 9 < 10. FOEN is still last-check / not public daily. The lock will refuse (good). Do not “fix” that by lowering the 10. Raise the harvest or add dated public non-NA networks.

11. **`overlap_report(..., min_stations=min(3, wide.shape[1]))` shrinks the concurrency denominator.** With 1 downloaded station, `days_with_min_stations` equals that station’s days (641 on the stale Rhône row). Script 62 still requires `n_stations >= 3` before `complete_enough`, so T8 is not currently counted. Keep `min_stations=3` even when the panel is thinner, so incomplete harvests cannot look 8-year concurrent.

12. **T5 matcher is not the locked topology match; do not flip `passed`.** After exact `n_sites` + ecoregion, `matched_contrast` falls back to `n_sites ± 1` with **no climate**. Donor count/direction and nearest-donor distance are absent. `regulated` is `frac_major_dam >= 0.5` on the GAGES-matched *subset* (Cahaba: 2/5 sites, 0.5 → regulated). Burned v1 IDs including `willamette_river_huc17` are in the 91-row table (only filenames containing `willamette_mainstem` are skipped). `t5_passed` is hardcoded False — keep it False until the match is the T5 spec.

13. **T6 “candidate zone” is claimed without BFI.** On-disk `matched_regulation_manifest.json` has `bfi_joined: false`, `seplains_is_candidate_failure_zone: true` (n_seplains=6), and `matched_regulation_networks.csv` has no `mean_bfi` column. Master-plan T6 prefers SEPlains × GAGES-II BFI. Do not title a failure zone from ecoregion membership alone.

14. **UK EA path (script 66 reads it) invents the query horizon and truncates.** `uk_ea_daily` queries hardcoded `2000-01-01`–`2024-12-31` (not a public first/last span) with `_limit=2000` and no pagination. Sub-daily series will silently keep the first 2000 points per year. Derwent is still a name cluster, not T8. Do not let a truncated overlap row become `complete_enough` for the 10 non-NA seats. Tests only `inspect.getsource` for the word “invented”.

---

## Accept as documented stop-loss

A. **Europe `complete_enough` is 0.** Manifest `countable_toward_t8: false`, `n_complete_enough: 0`, `europe_daily_years_invented: false`. Name clusters (`countable_public_daily: False` in `cluster_hubeau_rivers`) are not added to T8. Keep it that way until 3 stations share ≥8 overlapping *daily* years and ≥1825 concurrent days.

B. **T7 is not locked.** No `results/framework/public_rivers_v2/confirmatory_once.lock.json`. `write_lock_or_refuse` will not create one while `enough_to_lock` is false; a refusal sidecar is allowed. Do not lower floors to lock early. Do not open temperatures to assign IDs (proposal is metadata-only).

C. **Loire last-check is closed on the current caller path.** River column in `hubeau_all_stations.csv` is `la Loire`; `fullmatch (La\s+)?Loire` drops those 11 stations. Catalog v1 Loire Hub'Eau IDs are in `last_check_site_ids()`. Script 62 filters them. Do not download Loire to rescue Europe. Swiss FOEN stays uncountable until public dated daily history exists.

D. **Hub'Eau daily values are not invented.** Windows come from public `date_mesure_temp` first/last points, not catalog `None–None`. Empty windows return no rows. `resample("D").mean()` then `dropna` does not interpolate missing days. Instantaneous ≠ official Hub'Eau daily product; that label is already in the manifest (`instantaneous_resampled_to_daily_mean`). Do not promote `span_years` / `n_sites_span_ge_8yr` (5 instantaneous sites ≥8 years, `n_sites_daily_span_ge_8yr: 0`) into T8.

E. **`page * size > 20000` is not emitted.** URLs are `page=1&size=20000` (product = 20000, allowed). Tests lock `page=1` and no `page=2`. Live API 400s `page=2&size=20000`. Do not “fix” completeness by following `next`.

F. **`design_freeze_v4` was not retargeted.** `DEFAULT_DESIGN_PATH` / `EXECUTABLE_DESIGN_VERSION` remain v4; `SUPPORTED_EXECUTABLE_DESIGN_VERSIONS` is v2–v4 only. Next-paper freeze stays `configs/design_freeze_v9.yaml` via `DEFAULT_STUDY_FREEZE`. Dummy mismatch strings `design_freeze_v9` in historical tests are unused YAML loads. Do not add v9 to the executable set.

G. **T5/T6 are not passed.** Manifest `t5_passed: false`, `t6_passed: false`, `formal_evidence: false`. Five pairs and ΔR ≈ −0.03 are a development stop-loss, not a mechanism result. BFI failure is recorded (`bfi_joined: false`), not filled in.

H. **Honest public-USGS catalog remains 98 < 100 ≪ 150.** Do not paper that gap with 40 Hub'Eau name clusters, 5 instantaneous ≥8-year spans, UK EA Derwent, Loire, or Swiss.

I. **Script 66 does not rewrite `network_catalog_v1.yaml`.** Burned / last-check tokens block Jinsha, Chattahoochee, Willamette, Loire, Colorado from sealed IDs when the freeze loads. Keep evaluating once, after 40+10 real concurrent public networks exist.

---

## Attacks that do not land (this pass)

| Attack | Why it does not land *today* |
| --- | --- |
| Counting name clusters as T8 | `countable_public_daily` / `countable_toward_t8` false unless `complete_enough` |
| Locking now without 40+10 | No lock file; Europe complete_enough 0 |
| Inventing Hub'Eau daily years | First/last chronique timestamps; empty → no rows |
| Loire downloaded by script 62 | Name exclude + last_check site IDs |
| `page*size > 20000` in constructed URLs | Always page=1, size=20000 |
| Retargeting `design_freeze_v4` | contracts.py still v4 executable |
| Empty header cache treated as data | Unlinked; refetch in the unit test |

Those holds are flags and caller filters. The MUST-FIX list is what makes them reversible on the next run.

## Verdict

Do not count Hub'Eau or UK EA toward T8. Do not lock T7. Do not invent Europe years. Do not retarget v4. Implement real calendar-year windows, refuse last-check IDs in the fetch function, tombstone truncated caches/wides, and make the sealed *set* (not the eligible pool) carry 40+10 non-NA with a clamped boolean parse. Leave T5/T6 failed until the match is the written confound spec and BFI actually joins.
