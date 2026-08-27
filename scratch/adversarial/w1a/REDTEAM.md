# RED TEAM: W1-A HUC8 clustering (Implementer B)

Date: 2026-08-26
Role: adversarial hydrologist. Competing implementation under `scratch/adversarial/w1a/`. Production `src/`, `configs/`, `docs/`, `tests/`, `scripts/`, `paper/` were not edited.
Catalog: `results/framework/public_catalog/usgs_daily_temperature_series.csv` + `usgs_long_temperature_locations.csv`. No daily temperatures downloaded.

## Verdict

The reviewer’s **161** is not an exact overlap search and is not T2. On this catalog it is reproduced **exactly** by naive `str(huc).zfill(8)[:8]` (**161**). Official HUC prefixes + exact interval scan yield **166**. Truncating groups with >12 stations does **not** change the network count here (still 166) but **undercounts `n_stations` in 8 of 9 large groups**. `missouri_river_huc10` (18 stations, whole HUC2 10) splits into **12 HUC8 ids** and must not survive as one network. Catalog overlap is not qualified years. Loire/Swiss cannot fill the 10 non-NA sealed floor. never_sealed is inherited, not remapped.

---

## Exact counts (computed)

| Rule | 3st / 8y | 4st / 8y |
| --- | ---: | ---: |
| Official HUC8, exact subset | **166** | 105 |
| Truncated combo (n>12 → 12) | 166 | — |
| Naive `zfill(8)[:8]` HUC8 | **161** | — |
| HUC8 max_pair ≤ 100 km (filter, geodesic) | 150 | 95 |
| HUC8 max_pair ≤ 50 km (filter, geodesic) | 92 | 51 |
| Official HUC6-only | 145 | 110 |
| Official HUC4-only | 126 | 101 |
| name × official HUC2 (v2) | 98 | 44 |
| v1 name × raw prefix, whole-group overlap | 31 | 31 |
| On-disk v2 `huc8_only` 3st/8y | 166 | — |
| Reviewer figure | 161 | — |

- Exact − 161 = **+5**. `reviewer_161_equals_naive_zfill: true`.
- Exact − truncated network count = **0**.
- Groups with `n_stations_available > 12`: **9**. Truncation changes `n_stations` in **8** of them (caps at 12). Example: `huc8_03130001` keeps **28** under exact, 12 under truncation.
- Split SHA-256 (seed 20260826): `b11cd3f25605d629709661633191781fcde306677ed9fbf2590845d4b60211a3`
- Sealed in USGS-only draw: 56 (hits 40). Non-NA sealed: **0**. Shortfall vs 10: **10**. Loire/Swiss not used.
- never_sealed HUC8 rows held out: 19. None assigned `split_role=sealed`.

---

## Numbered holes

### 1. `huc.zfill(8)[:8]` is wrong on HUC12 / float / odd-length codes

On-disk HUCs include `3130004`, `3150202`, `190101060106.0`, `31602040402`, `nan`.

| Input | Naive `str(huc).zfill(8)[:8]` | `official_huc_prefix(huc, 8)` |
| --- | --- | --- |
| `3130004` | `03130004` (lucky) | `03130004` |
| `3150202` | `03150202` (lucky) | `03150202` |
| `190101060106.0` | `19010106` (lucky: first 8 chars) | `19010106` |
| `31602040402` (HUC12, leading zero dropped) | **`31602040`** | **`03160204`** |
| `float("031602040402")` → `31602040402.0` | **`31602040`** | **`03160204`** |
| `11000020108` | **`11000020`** | **`01100002`** |
| `nan` | `00000nan` | `""` (dropped) |

7-digit codes accidentally survive naive zfill. 11-digit HUC12s and float-coerced 12-digit codes do not. A toy of three stations whose HUCs are `031602040402` / `31602040402` / `31602040402.0` is **one** official HUC8 and **zero** naive groups (split below 3). That is the +5 vs 161.

**Naive implementer:** copies the reviewer’s one-liner, ships 161, documents “HUC8”.
**Merge:** keep `official_huc_digits` / `official_huc_prefix`. Do not add a `zfill(8)[:8]` helper “for the reviewer”.

### 2. Truncated combo search undercounts (even when the *count* does not move)

Reviewer truncated combinatorial search at 12 stations and called 161 a lower bound. Two different bugs hide in that sentence:

1. **Wrong HUC key** produced 161 (hole 1). Exact official HUC8 is 166.
2. **Truncation at 12** on *this* catalog does not drop any network (all nine large groups still have ≥3 concurrent stations among the 12 longest-span sites). It **does** cap `n_stations` at 12. Exact search keeps 28 in `huc8_03130001`, 19 in `huc8_03070103`, 18 in `huc8_17090004`, … Truncation reports 12.

A constructed 15-station HUC8 (12 long isolated records + a shorter concurrent triple) makes truncated search return **no network** while exact keeps the triple. That test is in `test_cluster_by_huc8.py`. Interval scan (`largest_overlapping_subset`) is exact and O(n²); combo search is not needed.

**Naive implementer:** `if n > 12: stations = stations[:12]` or skip the group, then copy 161.
**Merge:** reuse `largest_overlapping_subset`. Never truncate. Report 166, and report `n_stations_available` so a 31-station HUC8 is visible.

**Is 161 exact?** No. 161 is naive zfill. Exact is 166.

### 3. `missouri_river_huc10` must not survive as one HUC8

v1/v2 name×HUC2 lists 18 Missouri mainstem stations under HUC2 `10` (`missouri_river_huc10`). Official HUC8 splits those 18 site ids into **12** subbasins:

`10030101`, `10030102`, `10040104`, `10060001`, `10230001`, `10230006`, `10240001`, `10240005`, `10240011`, `10300101`, `10300102`, `10300200`.

Only two of those HUC8s currently form a 3st/8y cluster that still contains Missouri sites: `huc8_10230006` (4 stations, all named Missouri River, NLDI `flow_connected=true`) and `huc8_10300101` (5 stations, mixed Little Blue / Rock Creek / Missouri, NLDI `partial`). The other ten HUC8s are below the 3-station/8-year floor or are absorbed into mixed groups without enough Missouri overlap. There is **no** `missouri_river_huc10` row in the HUC8 table (`survives_as_one_huc8: false`).

**Naive implementer:** keeps the v2 candidate id, or groups by HUC2 while labeling the column `huc8`.
**Merge:** fail any PR that still emits `missouri_river_huc10` from `cluster_by_huc8`.

### 4. Pairwise distance is geodesic km, not degree span

Haversine, R = 6371 km. A 50 km cap in degrees is not a distance.

Same 0.6° of longitude:

- Florida 25°N: ~60 km → **fails** a 50 km cap
- Alaska 70°N: ~23 km → **passes** a 50 km cap

`lat_span_deg` / `lon_span_deg` (v1/v2 columns) cannot implement `max_pair_km`. Computed geodesic filters: 166 → **150** at 100 km → **92** at 50 km (omit groups that exceed the cap; default `distance_mode=filter`, not silent shrink).

**Naive implementer:** `max(lat)-min(lat) < 0.45` or `* 111` as if the Earth were a cylinder at the equator.
**Merge:** haversine; document filter vs shrink. Filter is the honest default because shrinking invents a different network than the max-overlap subset.

### 5. Missing lat/lon must not become 0 or inf

Policy encoded in `pairwise_geodesic_stats`:

- 0 or 1 located station: `max_pair_km = NaN`, `coord_policy` in `{no_coords, single_coord, single_station}`
- Partial coords: max over located pairs only, `coords_incomplete=true`
- Distance cap: unlocated stations are **dropped**, overlap is re-validated on located stations; they are not treated as 0 km (always pass) or inf (always fail)
- Never emit non-finite `max_pair_km`

On the live catalog every kept HUC8 had complete coordinates (`coord_policy=complete`, 0 NaNs). The policy still has to be in the function: the next catalog extract will not be that clean.

**Naive implementer:** `fillna(0)`, `np.nanmax` turning all-NaN into 0, or `max_pair_km=inf` when any coord is missing so the cap always drops the group.
**Merge:** take this policy verbatim.

### 6. HUC8 can contain two unconnected creeks. NLDI is a covariate, not a delete

Live probe (cached under `nldi_cache/`, not a 161-call hammer):

| network_id | n_stations | NLDI | n_connected | kept? |
| --- | ---: | --- | ---: | --- |
| `huc8_03130001` (Chattahoochee + Peachtree + Suwanee Creek, 28 stations) | 28 | **partial** | 14 | yes |
| `huc8_10300101` (Little Blue / Rock Creek / Missouri) | 5 | **partial** | 2 | yes |
| `huc8_10230006` (Missouri only) | 4 | **true** | 4 | yes |

`huc8_03130001` is the textbook mixed HUC8. Parser handles `USGS-` prefix, int ids, empty FeatureCollections, HTTP 404 (isolated origin, `flow_connected=false`, group **kept**), HTTP 429 (retry / `rate_limited` → `not_queried`, not faked). Remaining 163 groups are `not_queried` on purpose (Implementer A owns full NLDI).

**Naive implementer:** `if not flow_connected: drop`; ignore 404; compare `USGS-01608500` to `01608500` as unequal; treat empty FeatureCollection as API failure and fabricate connectivity.
**Merge:** `spatially_proximate_not_flow_connected` column. Do not filter on it for inventory counts. Cache JSON. Do not fake the 163.

### 7. Catalog overlap ≠ qualified years. T2 is not done at 161 (or 166)

`daily_begin`/`daily_end` are first and last catalog dates. They are not same-day completeness, not QC, not 2000–2024. The 12 downloaded rivers already collapsed 12→6 under a same-day rule. Expected post-download attrition 25–40%:

- 166 × 0.65 ≈ 108 (clears `n_networks_min=100` only as a hope)
- 161 × 0.65 ≈ 105 (same)
- 150 still needs Europe and/or a documented 3st/6y failure-closure

**Naive implementer:** feasibility sentence “161 candidate networks, already ≥150, T2 is in reach.”
**Merge:** copy the competing `feasibility.md` honesty block. Headline is grouping-rule correction, not inventory.

### 8. Split must not seal never_sealed. Loire/Swiss cannot fill 10 non-NA

SHA-256 assignment `sha256(f"{seed}\\t{network_id}")` inside climate_band × size tertile, seed **20260826**, locked **before** download.

never_sealed matched by v1 site overlap (and conservatively by name tokens on mixed HUC8s): 19 HUC8 rows `never_sealed_held_out`, including `huc8_03130001` / `huc8_03130002` (Chattahoochee), Delaware HUC8s, Willamette/McKenzie HUC8s, Madison, Mahoning, Cahaba, Santa Fe, Roanoke, Yellowstone, Clearwater, Suwannee. Name-token over-flag of mixed basins (`huc8_17090001` with empty `never_sealed_v1_ids`) is the **safe** direction. Do not seal them.

Loire and Swiss are **absent** from the USGS HUC8 table and were **not** inserted. `n_non_na_sealed = 0`. The 10 non-NA floor is a recorded shortfall, not a pad. USGS-only sealed count is 56 (the 40 absolute floor is hit; the 10 non-NA floor is not).

Regulation stratum is `unknown_until_gages`. The 335-row regulation-panel extract is not catalog-wide GAGES-II. Do not invent `regulated` from the word “Missouri”.

**Naive implementer:** 50/20/30 over the full 166 including Chattahoochee 03130001; put Loire/Swiss in sealed “for continents_min=2”; hash after download; stratify on river-name dams.
**Merge:** site-overlap never_sealed, SHA-256 table before any NWIS pull, leave non-NA shortfall in writing.

### 9. Do not remap `network_catalog_v1`. Do not download temperatures

Competing artifacts live only under `scratch/adversarial/w1a/`. `sealed_outcomes_opened: false`. `temperature_record_unverified: true`. Default catalog path untouched.

**Naive implementer:** `scripts/51` rebuild from the new 166; download “just to check overlap”; retokenize `delaware_river_huc20` to `huc8_02040101`.

---

## Predicted production bugs Implementer A will ship

1. **Document `official_huc_prefix` and still `zfill(8)[:8]`** in the builder or a pandas `.str.zfill(8).str[:8]` on the raw column. Symptom: count **161**, not 166.
2. **Copy 161** into feasibility / catalog v3 YAML as if computed.
3. **Truncate at 12** “because the reviewer did.” Network count may still be 166; `n_stations` on Chattahoochee HUC8 will be 12 instead of 28.
4. **Degree span as km.** Alaska groups die; Florida groups that should die survive (or the reverse). 50 km filter will not land on 92.
5. **`max_pair_km = 0` or `inf`** when a station lacks coordinates.
6. **Silent shrink** of huge overlap subsets to meet the cap, then call the result “the max-overlap subset.”
7. **Drop NLDI `false`/`partial` groups.** Chattahoochee `huc8_03130001` disappears; count falls well below 166.
8. **404 → drop or `not_queried` with fabricated empty connectivity.** Isolated sites are real origins.
9. **String-match site ids without stripping `USGS-` / int / leading-zero variants.** Everything looks disconnected.
10. **Claim T2 / “already ≥150”** from catalog span. 166 is not qualified years.
11. **Seal `huc8_03130001`** because the network_id changed from `chattahoochee_upper_middle`. Site overlap still hits confirmatory stations `02334430`…`02337170`.
12. **Insert Loire/Swiss** to make `sealed_min_outside_north_america: 10`.
13. **Remap `network_catalog_v1.yaml`** or change `DEFAULT_CATALOG`.
14. **Download daily temperatures** “to verify” HUC8 overlap.
15. **Use the 335-row GAGES extract as a complete regulation stratum**, or label “Missouri” as regulated from the name.
16. **Write `huc8` as int** in CSV/YAML so `03130001` becomes `3130001`.
17. **Hash the split after** assigning roles by CSV sort order instead of SHA-256 within strata.
18. **Keep `missouri_river_huc10`** as a v3 candidate.
19. **Add HUC8 counts to name×HUC2 98** and call it 264 independent networks.
20. **Skip `n_stations_available` and `overlap_start`/`overlap_end`**, so truncation and window honesty cannot be audited.

---

## Recommended merge into production

Take, as-is in spirit:

- `cluster_by_huc8` signature, official HUC encoder, exact `largest_overlapping_subset`, `n_stations_available`, `overlap_start`/`end`, geodesic `max_pair_km`, missing-coord policy, `distance_mode=filter`
- `nldi_connectivity.parse_nldi_feature_collection` + 404/429/empty-FC behavior + “do not drop”
- Feasibility honesty: 166 exact, 161 = naive zfill, catalog ≠ qualified years, Missouri 12-way split, non-NA sealed shortfall = 10
- Split lock: SHA-256 before download, never_sealed by **site overlap**, Loire/Swiss absent

Do not merge:

- Naive zfill encoder except as a **contrast count**
- Truncated combo as the production search
- Name-token never_sealed as the only matcher (keep site overlap; tokens are a backstop)
- Live NLDI of all 166 from this scratch cache as a complete covariate (A owns that pass; 3 groups here are a client proof)

Tests to land in `tests/test_catalog_v3_huc8.py`: naive zfill fails on 12-digit/float HUC12; 13 concurrent stations stay 13; truncated 15-station trap; Alaska vs Florida 50 km; missing coords are NaN; NLDI fixture 404/empty/`USGS-`; Missouri not one HUC8; v1 signature unchanged.

---

## Files

```
scratch/adversarial/w1a/
  cluster_by_huc8.py
  nldi_connectivity.py
  test_cluster_by_huc8.py          # 15 passed
  REDTEAM.md
  feasibility.md
  counts.json
  missouri_split.json
  usgs_river_clusters_v3_huc8.csv
  usgs_river_clusters_v3_huc8_maxpair50.csv
  usgs_river_clusters_v3_huc8_maxpair100.csv
  usgs_river_clusters_v1_name_huc2_contrast.csv
  catalog_v3_split.csv
  catalog_v3_split_sha256.txt
  network_catalog_v3_split.yaml
  nldi_cache/                      # 3 sites × UM+DM
```
