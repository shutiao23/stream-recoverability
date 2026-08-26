# RED TEAM: Phase 3 catalog expansion

Date: 2026-08-26
Role: attack completeness, overclaim, and hidden shrinkage. Not a patch.
Target: `src/stream_recoverability/data/public_river_inventory.py` `cluster_rivers_from_catalog`, `results/framework/public_catalog/usgs_river_clusters.csv`, `results/framework/public_catalog/feasibility_decision.md`, `configs/design_freeze_v9.yaml` `inventory_targets` / `never_sealed_networks`, `paper/next/results.md` (31 USGS / 6 concurrent).
v2 cluster files: **do not exist**. No `usgs_river_clusters_v2.csv`, no second clustering function, no HUC8 expander, no quality-flag table. This pass attacks the algorithm that would be reused, plus the required algorithm Phase 3 still owes.
Sealed last-check temperatures were not opened for this review.

## Verdict

Phase 3 did not ship a catalog expansion. It left a name-plus-broken-prefix grouper that scores **catalog date-span intersection**, then wrote **31** as the method-eligible USGS ceiling. `paper/next/results.md` is honest about the 12→6 collapse after download. `feasibility_decision.md` and `national_catalog.json` are not: they still treat those 31 span-overlap groups as rivers you can use to fit or lock. Six of the 31 were already downloaded and failed same-day four-station overlap. Several of the remaining 25 are not the same river, not four stations, or not alive in 2000–2024.

HUC8-only grouping was **not** implemented. The live rule is `river_name` + first two characters of an **unpadded** HUC string. That is neither HUC2 nor HUC8. Switching to HUC8-only, as a v2 might, would split real mainstems and glue tributaries. Do not “fix” 31 by cutting HUC8s.

Loire and Swiss are not in the 31. A leftover summary still writes Loire as 14 stations with eight-year daily temperature. The 12 burned rivers were not remapped to sealed and their daily files are the only NWIS downloads present. 150 is still a target, not an inventory, in the next-paper files. Script `51_apply_catalog_clusters.py` can still evict burned IDs and promote never-downloaded span groups on the next run.

---

## 0. What exists (and what does not)

Present:

- `cluster_rivers_from_catalog` (`public_river_inventory.py:517-580`): groupby `(river_name, huc.str[:2])`; `enough_overlap_years` = `(min end − max begin) ≥ 8`.
- `results/framework/public_catalog/usgs_river_clusters.csv`: 49 rows with ≥4 long series; 31 with `enough_overlap_years=True`.
- `feasibility_decision.md`: headline 31; table **30** rows (`scripts/49_national_temperature_catalog.py:87` slices `build[:30]`; Animas 8.51 yr is dropped).
- `paper/next/results.md:7-21`: 3995 series / 1648 with ≥8 yr span / 31 span groups / 12 downloaded / 6 concurrent-enough.
- Freeze `never_sealed_networks` (`design_freeze_v9.yaml:139-153`): Jinsha, Chattahoochee, and the 12 downloaded IDs. Loire / Swiss on `not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public`.
- `inventory_targets.independent_networks: [150, 250]` (`yaml:168-186`) still labeled as design targets, not current stock.

Absent (required for Phase 3, `docs/v9_redesign_master_plan.md:85`):

- Any `*clusters*v2*` or HUC8 cluster table.
- A concurrent-day field on the 31 (`days_with_min_stations`, `complete_enough`).
- A same-river / collocated / nested-tributary quality flag.
- A `validate_catalog` update from 4 stations / 4 climates to the freeze’s 3 / 3 (`network_catalog.py:62-82` vs `yaml:169-173`).
- A test of `cluster_rivers_from_catalog`. `tests/test_public_river_inventory.py` only checks `river_name_from_site_name` on four titles.

If Blue ships v2 as “HUC8-only, keep span overlap, call it 150,” every attack below still holds.

---

## 1. Catalog span overlap is not download-concurrent (the 12→6)

`cluster_rivers_from_catalog` (`public_river_inventory.py:541-567`):

```text
overlap_start = begins.max()
overlap_end   = ends.min()
enough_overlap_years = (overlap_end - overlap_start).days / 365.25 >= 8
```

That is the intersection of **metadata begin/end**. It does not ask whether four stations have a value on the same day.

After download, `overlap_report` (`public_temperature.py:123-160`) does ask:

```text
good = (wide.notna().sum(axis=1) >= 4)
complete_enough = (years >= 8) and (good.sum() >= 5 * 365)
```

`results/framework/public_rivers/overlap.csv` already applied that rule to the 12. Only Delaware, Willamette, Madison, Mahoning, Roanoke, Santa Fe pass. Suwannee, Yellowstone, Rio Grande, Cahaba, McKenzie, Clearwater fail. Clearwater fails by **one day** (1824 vs 1825). Yellowstone has catalog span 19.1 yr and 1350 concurrent-four-station days.

`paper/next/results.md:17-21` writes this collapse in plain language. The catalog artifacts do not:

| Artifact | What it still says |
| --- | --- |
| `feasibility_decision.md:5,8,14-47` | “USGS … 同期够八年、至少四站的河：31 条”; “可以考虑用来定方法或锁设定的：31 条”; Yellowstone listed at 19.1 yr |
| `national_catalog.json` | `n_river_groups_eight_year_overlap: 31` |
| `docs/network_catalog_feasibility.md:5` | same 31 |
| `scripts/51_apply_catalog_clusters.py:80,90` | `feasibility_status: catalog_overlap_checked`; first 8 of the 31 → `use: build` |

So the 31 is still the **method-eligible** list. Six members of that list are already known not to be download-concurrent. The other 25 have never been put through `overlap_report`.

Span intersection is also the wrong window:

| Cluster | Catalog span used for the 31 | Why it is not a 2000–2024 four-station panel |
| --- | --- | --- |
| Truckee | 1989-08-26 – 1998-09-29 (9.1 yr) | Dead before the download window |
| James River (Dakotas) | 1985-10-10 – 1994-09-30 (9.0 yr) | Dead before the download window |
| Reedy Creek | 1985-01-24 – 2001-05-11 (16.3 yr) | Ends 2001; Disney-area creek |
| Wichita | 1998-09-30 – 2011-09-29 (13.0 yr) | Mostly pre-2012 |
| Delaware (ALL-CAPS row) | 1993-08-11 – **2007-05-07** (13.7 yr) | Forced by `01427301` catalog end. Download 2000–2024 still found 8857 days with ≥4 of 7 stations. Catalog ∩ ≠ concurrent days. |

**Must-fix:** a cluster row is not inventory until `overlap_report` (or an equivalent daily check) passes. Keep 31 as “catalog span only.” Do not feed `enough_overlap_years` into build/lock. Do not list Yellowstone at 19.1 yr as method-eligible after `overlap.csv` already failed it.

---

## 2. They did not group by HUC8. HUC8-only would invent rivers. The live rule already invents some.

Docstring (`public_river_inventory.py:525`): “Group … by watercourse name and HUC2.”
Code (`533-538`): `merged["huc2"] = huc.str[:2]`.

Location HUCs are not zero-padded and not one level:

| Site | Stored `huc` | `huc[:2]` written as `huc2` | Real HUC2 |
| --- | --- | --- | --- |
| `01427301` Delaware near Hankins | `2040101` | `20` | `02` |
| `02423130` Cahaba | `3150202` | `31` | `03` |
| `0208062765` Roanoke | `3010107` | `30` | `03` |
| `03086500` Mahoning | `5030103` | `50` | `05` |
| `14158100` Willamette | `17090003` | `17` | `17` (no leading zero, accident) |
| `06470500` James at Lamoure | `101600030804.0` | `10` | `10` (float leak) |
| `01463500` Delaware at Trenton | `20401050911` | `20` | `02` (HUC12, no leading zero) |

`never_sealed_networks` locked the broken tokens: `delaware_river_huc20`, `cahaba_river_huc31`, `mahoning_river_huc50`, `suwannee_river_huc31`. Script 51’s climate map (`HUC_CLIMATE`) keys `"03"`, `"05"`, `"02"`. A Cahaba row with `huc2="31"` becomes `climate_or_ecoregion: unspecified`.

Name parse leftovers counted as networks: `TRUCKEE RV`, `Wichita Rv`, `COOPER R`, `SAN JOAQUIN R`.

Fake or non-network groups **already in the 31**:

1. **Klamath (20.7 yr, 4 IDs).** `420853121505500` and `420853121505501` are the same point (Miller Island boat ramp, surface vs bottom; `usgs_long_temperature_locations.csv` same lat/lon `42.14805556, -121.848611`, same HUC `18010204`). The other two are Keno dam pool (`11509370`, `11509500`), ~3 km apart. `lat_span_deg=0.020`. This is a tailrace, not a four-station river.
2. **Reedy Creek (16.3 yr).** Four Disney-area Florida sites, `lat_span=0.073`, `lon_span=0.037`. Not a recoverability network.
3. **Cooper R (10.1 yr).** Name truncated. Four tidal/harbor sites, `lon_span=0.040`.
4. **Yellowstone / Rio Grande.** One USGS name, hundreds of kilometres (`lon_span` 6.64° and `lat_span` 4.07°). Already failed concurrent download. Still in the 31.

HUC8-**only** (no name), if that is the missing v2, creates the other error:

- Same HUC8 holds mainstem plus named tributaries (`11010001` is White River near Fayetteville **and** West Fork White River).
- One mainstem spans many HUC8s: White River AR is `11010001` / `11010003` / `11010004`; Yellowstone is `10070002` (Corwin Springs) vs `10100004` (Sidney); Delaware is `02040101` vs `02040104` vs `02040105`. HUC8-only would report three “Delaware networks” from one river.
- Same station can carry HUC8, HUC12, or unpadded HUC7 (`2040101` vs `20401050911` vs name-search `020401010501`). A HUC8 cut on those strings is three different keys.

Name + real HUC2 is not enough either. It correctly splits White River AR (`huc11`) from White River CO/UT (`huc14`) and Cedar River WA from Cedar River FL. It still counts McKenzie and Willamette as two independent units in HUC17, and Santa Fe and Suwannee as two in the broken `31` bucket. Those are nested. Cluster bootstrap over “networks” would treat them as independent.

**Must-fix:** v2 groups by the same watercourse (normalized name + topology / drainage), not by HUC8 and not by `huc.str[:2]`. Zero-pad HUC to 8 or 12 before any prefix. Collapse surface/bottom and other collocated IDs. Flag nested tributaries so they cannot both be independent units. Do not relabel the burned 12 to padded HUC2 IDs without a map; the freeze tokens are already `*_huc20` / `*_huc31` / `*_huc50`.

---

## 3. Loire / Swiss were not added to the 31. A leftover file still counts Loire as public daily.

Honest in this pass:

- `feasibility_decision.md:9-10,53-67`: Hub'Eau 871 / Loire-exact 11 with `None–None` dates; FOEN 246 names; “这次没有日均水温.”
- `paper/next/results.md:11-12`: no date spans; Swiss daily must be ordered; not downloaded.
- `loire_hubeau_stations.csv`: 11 rows, empty `begin`/`end`.
- Freeze `not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public`.
- `network_catalog_v1.yaml` Loire / Swiss: `catalog_names_only_no_date_span` / `locations_only_daily_history_not_public`, `use: last_check`.

Dishonest leftover:

- `river_catalog_summary.csv` row `loire_mainstem`: `n_with_daily_temperature=14`, `n_with_8yr_daily_temperature=14`, `enough_stations=True`. Site IDs are USGS-shaped (`06182045`, `06177959`, `04154050`, `02047500`, …), not the Hub'Eau Loire set (`04000100` … `04134700`).
- `catalog_check.json`: `loire_public_stations_listed: 14` against the later exact-name 11.

If Phase 3 v2 reads `river_catalog_summary.csv` or `catalog_check.json`, Loire becomes a 14-station, eight-year public-daily network. That is the T8 / ≥10 non-NA sealed pad the freeze already forbade.

**Must-fix:** tombstone or rewrite `river_catalog_summary.csv` and `catalog_check.json`. No inventory path may increment `n_with_daily_temperature` for Loire or Swiss until dated public daily series exist. Do not count either toward T8 or the 10 non-NA sealed seats.

---

## 4. Burned rivers were not remapped to sealed. The remapper can still drop them.

Current `network_catalog_v1.yaml`: the 12 downloaded IDs are `development` / `validation`, `use: build` / `lock`. Jinsha and Chattahoochee are `historical`. Colorado, Columbia, Loire, Swiss, Ohio, Deschutes are `sealed` / `last_check`. No burned ID has `split_role: sealed`.

Script 51 (`151-158`) refuses to **write** sealed roles for `never_sealed_networks`. It does not **keep** those IDs.

On a re-run it (`scripts/51_apply_catalog_clusters.py:92-108`):

- Drops every existing network that is not `historical_seen` or `use == last_check`.
- Rebuilds build/lock from cluster CSV order: first 8 of `enough_overlap_years`, next 4.
- Sets `historical_seen: False` on every new row.

Sorted 31 starts Au Sable (8), Delaware (7), Yellowstone (6), Mahoning (6), Willamette (6), Clark Fork (6), White River AR (6), Roanoke (5), … Suwannee is 30th. A re-run would **evict** Suwannee, Cahaba, McKenzie, Santa Fe, Clearwater from the catalog and **promote** Au Sable, Clark Fork, White River, Waccamaw, San Juan — none of them download-concurrent. Evicted burned IDs are then missing from the catalog, so a later Phase 3 pass can add them as sealed without tripping the “do not write sealed roles” check.

Script 45 (`57-63`) only asserts four of fourteen burned freeze IDs exist on the freeze list, not that the catalog still holds all twelve as non-sealed.

**Must-fix:** pin the fourteen freeze IDs in the catalog with immutable `split_role`. Script 51 must not drop or reassign them. Script 45 must assert the full set is present and not sealed.

---

## 5. Sealed last-check temperatures were not downloaded

`data/public_rivers/nwis/` has only the 12 burned rivers’ stations (2000–2024). No Colorado, Columbia, Ohio, Deschutes, Loire, or Swiss daily files. `public_river_check.json`: `last_check_temperatures_used_to_score: false`. `national_catalog.json`: `last_check_temperatures_opened: false`.

This attack does not land as a completed leak.

Residual: `09379500` (San Juan near Bluff) is a **sealed Colorado** candidate (`network_catalog_v1.yaml:199`) **and** a San Juan row in the 31 (`usgs_river_clusters.csv` `san_juan_river_huc14`). Downloading San Juan as a “new” build river opens a temperature series that the sealed Colorado list already named. `data/public_rivers/usgs/14152000_*.csv` is an older Willamette mainstem file not in the current six-station cluster; not sealed, but another ID-space.

**Must-fix:** a station on a `last_check` / sealed candidate list cannot enter a development cluster or a new download list. v2 must have a unique-station constraint before any NWIS pull.

---

## 6. 150 is not written as if it exists. It is still written as if Phase 3 will produce it.

`paper/next/results.md`, `paper/next/claim_matrix.md`, `paper/next/manuscript_skeleton.md`, and charter §现在做到哪 do **not** claim 150 rivers are in hand. They write 31 / 12 / 6 and “没有 150 条河.”

What is still wrong for Phase 3:

- T2 and `inventory_targets` still require ≥150 / CI at ≥100 (`yaml:117-121,168-186,197`). Phase 3’s only new number is 31 catalog-span groups, of which 6 are concurrent. There is no v2 path from 31 to 150 that is not HUC8-splitting (attack 2) or counting Loire/Swiss (attack 3).
- Charter §怎样算过关 still leads with “独立河网目标 ≥150” as a pass rule. The failure hatch is “合格河网不到 100 条：放松到 3 站 / 6 年.” Relaxing the station floor does not create 94 new rivers. The 31→6 rate says most span groups will not survive download.
- `feasibility_decision.md` “31 条 … 可以考虑用来定方法” is the sentence that will get cited as inventory if 150 stays in the same paragraph as T2.

**Must-fix:** keep 150 as a target only. Every Phase 3 artifact that prints a count must print **31 catalog-span / 6 download-concurrent** as the audited maxima. Do not imply the 31 are the first slice of 150.

---

## 7. Same stations, two groupings

Live collisions (not hypothetical HUC8):

1. **`delaware_river_huc20` twice.** `DELAWARE RIVER` (7 sites, 13.7 yr, in the 31) and `Delaware River` (5 sites: Frenchtown / Trenton / Easton / …, overlap 0). `groupby` is case-sensitive; `_network_id` lowercases. Same ID, two rows, disjoint IDs, one river. `river_catalog_summary.csv` `delaware_mainstem` already mixes them (`01427510,01434000,01463500`).
2. **`09379500`.** San Juan 31-list **and** `colorado_grand_canyon` sealed candidates **and** the stale Colorado summary row that claims 12.6 yr common overlap (`river_catalog_summary.csv`) while `usgs_river_clusters.csv` Colorado is 0.0 yr and the catalog note says no eight-year window.
3. **Nested pairs counted twice as independent networks:** McKenzie ⊂ Willamette (both downloaded; McKenzie failed concurrent, Willamette passed); Santa Fe ⊂ Suwannee (both downloaded; opposite concurrent result); Animas ⊂ San Juan (Animas is the 31st span group, sliced out of the table).
4. **Klamath surface/bottom** counted as two of four stations (attack 2).

A HUC8 v2 on unpadded strings would add a fifth: `2040101` vs `20401050911` vs `020401010501` as three “HUC8s” for Delaware stations that already sit in two name-case groups.

**Must-fix:** one station, one network. Casefold names before group and before ID. Deduplicate IDs across the whole catalog. Nested tributaries share a unit or are flagged `not_independent`. Do not assign a sealed-list ID to a build cluster.

---

## Required algorithm (v2 does not exist; do not ship HUC8-only)

Phase 3 still owes (`master plan` phase 3: public catalog expansion, sealed lock, quality flags; freeze: update the 4-station validator). The function that must exist is not `groupby(huc8)`.

Required v2 cluster table, one row per **same river**:

| Field | Rule |
| --- | --- |
| `river_key` | Casefolded, abbreviation-normalized name (`RV`/`R` → River) plus topology or drainage, not HUC8. |
| `huc8_padded` / `huc2_padded` | Zero-pad stored HUC to 8 or 12; HUC2 = first two of that. Do not cut raw `huc.str[:2]`. |
| `site_ids` | Unique globally. Collapse collocated / surface-bottom. No ID that appears on a sealed or last-check list. |
| `catalog_span_years` | `min(end)−max(begin)` only. Label `catalog_only`. |
| `concurrent_days` / `complete_enough` | Same-day ≥ `stations_per_network_min` (freeze scientific floor is 3; validator still says 4). Not inventory until this passes, or the row stays `catalog_only`. |
| `independent_unit` | False if nested in another kept mainstem. |
| `countable_public_daily` | False for Loire, Swiss, and any series without public dated daily values. |
| `never_sealed` | Copied from the freeze; immutable. |
| `split_role` | Not assigned by CSV sort order. |

Forbidden in v2:

- Treating `enough_overlap_years` as download-concurrent.
- HUC8-only groups (different rivers, one subbasin; one river, many subbasins).
- Writing 150, or 31, as concurrent inventory.
- Downloading last-check temperatures to “check” overlap.
- Remapping or dropping freeze burned IDs.
- `build[:30]` while the count says 31.
- Reading `river_catalog_summary.csv` as the Loire daily record.

`validate_catalog` must move to the freeze’s 3 stations / 3 climates in the same change, or script 45 will fail the first real 3-station add (`known_contract_lag` is not a ticket).

---

## Must-fix list

1. **Stop using catalog span as method-eligible inventory.** `enough_overlap_years` is not `complete_enough`. Rewrite `feasibility_decision.md` / `national_catalog.json` so the 31 are span-only. Keep the 12→6 as the only download-concurrent count. Do not list Yellowstone, Suwannee, Rio Grande, Cahaba, McKenzie, Clearwater as build/lock after `overlap.csv` failed them.

2. **Do not ship HUC8-only v2.** Group by the same watercourse (normalized name + topology). Zero-pad HUC. Collapse Klamath Miller Island surface/bottom and other collocated IDs. Flag McKenzie/Willamette, Santa Fe/Suwannee, Animas/San Juan as not independent. Kill `TRUCKEE RV` / `COOPER R` parse leftovers. Do not silently retokenize locked `*_huc20` / `*_huc31` / `*_huc50` IDs.

3. **Tombstone the Loire-as-daily leftovers.** `river_catalog_summary.csv` and `catalog_check.json` still imply Loire has 14 eight-year daily stations. Freeze exclusion must be executable in every inventory reader.

4. **Make `never_sealed_networks` catalog-executable.** Script 51 must not drop or reassign the 14 IDs. Script 45 must assert all 14 are present and not sealed. Do not fill sealed seats with Colorado/Columbia (no eight-year window) or Loire/Swiss (no public daily).

5. **Unique station constraint before any new download.** `09379500` cannot be both San Juan-build and Colorado-sealed. Do not pull last-check temperatures to inflate overlap.

6. **Keep 150 as a target only.** Phase 3 artifacts must print 31 span / 6 concurrent as the audited maxima. No sentence that reads as if 31 is the first block of 150.

7. **Deduplicate IDs and case.** Two `delaware_river_huc20` rows is a collision. Casefold before `groupby` and before `_network_id`. One station, one network.

8. **Write the missing v2 table and tests.** No `*clusters*v2*` exists. Add a test that: span overlap ≠ concurrent days (use the 12→6); unpadded `2040101` is not HUC2 `20`; surface/bottom is one site; Loire has no daily span; burned IDs cannot become sealed; `build[:30]` cannot disagree with the headline count.

9. **Close the 4-vs-3 validator lag in the same Phase 3 change** that first adds a 3-station network, or do not add one.

---

## What this pass does not claim

`paper/next/results.md` did not pretend the 31 were already download-concurrent. It did not write 150 as stock. It did not score Loire/Swiss daily. The 12 burned rivers were not moved to sealed, and last-check daily files are not in `data/public_rivers/nwis/`. Those are the honest sentences. They do not make the 31 a corpus, and they do not replace the missing v2 algorithm.
