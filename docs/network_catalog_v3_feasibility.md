# Catalog v3 feasibility (HUC8 grouping-rule correction)

This is a station-year inventory, not a recovery score. Daily temperature
values were not downloaded. Sealed temperatures were not opened. The 12
already-downloaded rivers and Jinsha / Chattahoochee were inherited as
`never_sealed` and were **not** remapped into sealed. Loire and Swiss
Aare-Rhine are **not** in this USGS HUC8 catalog and still cannot count
toward T8 or the 10 non-North-America sealed networks until public dated
daily values exist.

## This is a grouping-rule correction, not a relaxation

v1 and v2 name×HUC2 group by watercourse name inside a 2-digit region.
That both splits real networks (renamed tributaries) and invents fake ones
(one Missouri-in-HUC2-10 cluster spanning many subbasins). HUC8 grouping
is spatially **stricter**: it is a subbasin, not a region. Official USGS
HUC prefixes are used (`official_huc_prefix`). The reviewer's
`str(huc).zfill(8)[:8]` is the intent for 7-digit codes such as `3130004`;
`official_huc_prefix` is the correct implementation for catalog values
such as `190101060106.0` and `11000020108`.

Within each HUC8, `largest_overlapping_subset` keeps the largest set whose
interval intersection is at least T years. The search is exact (interval
scan over begin dates). **Nothing was truncated at 12 stations.** A
truncated combo search (n>12 → 12) still yields the same *network* count
on this catalog (**166**); it only undercounts `n_stations` inside large
groups. The reviewer's published **161** is reproduced exactly by naive
`str(huc).zfill(8)[:8]`, not by truncation.

- Exact HUC8 3-station / 8-year count (`official_huc_prefix`): **166**.
- Naive `zfill(8)[:8]` HUC8 3-station / 8-year count: **161**.
- name×HUC2 `missouri_river_huc10` has 18 catalog stations; those stations occupy 15 HUC8 codes (10030101, 10030102, 10040104, 10060001, 10110101, 10130101, 10170101, 10230001, 10230006, 10240001, 10240005, 10240011, 10300101, 10300102, 10300200). 3 of those HUC8s currently form a 3-station/8-year cluster that still contains Missouri sites (huc8_10170101, huc8_10230006, huc8_10300101). The name×HUC2 token does not survive as one HUC8 network.

## Catalog span is not data density

`daily_begin` / `daily_end` are first/last catalog dates. Qualified years
happen after download and QC. Expected post-download attrition is 25–40%.
166 × 0.65 ≈ 108 still clears `n_networks_min` 100 if that attrition
holds. 150 still needs Europe and/or a documented 3-station / 6-year
failure-closure. This file does not relax T2.

## Counts

| grouping | 3 stations / 8 years | 4 stations / 8 years |
| --- | ---: | ---: |
| name×HUC2 (v2 subset, official HUC2) | 98 | 44 |
| HUC4-only (official prefix, exact subset) | 126 | 101 |
| HUC6-only (official prefix, exact subset) | 145 | 110 |
| HUC8-only (official prefix, exact subset) | 166 | 105 |
| HUC8 naive zfill(8)[:8] (diagnostic, not the rule) | 161 | — |
| HUC8, max pairwise ≤ 100 km | 150 | 95 |
| HUC8, max pairwise ≤ 50 km | 92 | 51 |

v1 name×HUC2 whole-group overlap (4 stations / 8 years, raw HUC prefix): 31.

Spatial-filter policy: compute the overlap subset first, then **omit**
groups whose maximum pairwise geodesic distance (haversine, Earth radius
6371 km) exceeds the cap. Groups are not silently shrunk.

Long-station filter: catalog span ≥ 8 years, matching the v2 builder's
8-year case. Stream / ST / Streamgage only.

## NLDI flow connectivity

HUC8 does not guarantee flow connectivity. Each group is queried from its
median station (lat, then lon, then site_id) on NLDI UM and DM at 200 km.
Disconnected groups are **retained** as covariate
`spatially_proximate_not_flow_connected` (true when NLDI status is
`false` or `partial`). Connectivity is not faked.

- queried distance: 200 km
- true (all other stations on UM∪DM): 41
- partial: 93
- false (none besides origin): 24
- not_queried (API failed after retries; cache of successes kept): 8
- cache directory: `results/framework/public_catalog/nldi_cache`
- Wrote/reused 316 cached NLDI JSON files. Failed live queries are not_queried and were not cached as successes.

## Split lock (before any new download)

- seed: 20260826
- SHA-256 of canonical split table: `2405169325fecaeb24bea9a5c9fc5ea66e303c14e41def1e3d32f6853679c1f1`
- split pool (excluding never_sealed and historical): 147
- development / validation / sealed: 74 / 29 / 44
- assignment: shuffle inside climate × size strata, then cut 50/20/30 on the concatenated order so small strata cannot dump remainders into sealed.
- never_sealed excluded from random split: 17
- historical excluded from random split: 2
- sealed ≥ 40 is a **target after Europe**. USGS-only sealed count is 44.
- non-North-America sealed: 0 (target 10). Loire/Swiss were not placed in sealed.
- regulation_stratum: GAGES-II hydromod_dams is on disk; regulation_stratum is regulated / unregulated / unmatched_gages from MAJ_NDAMS_2009. Incomplete until every candidate STAID matches.
- USGS-only sealed is 44, which meets the numeric 40 floor before Europe, but this is still a catalog-span lock, not a qualified-year lock. non-North-America sealed is 0 vs target 10; Loire/Swiss were not inserted to close the gap.

Strata for the random assignment are climate_band (HUC2 map from
scripts/55) × network-size tertiles (`rank(method='first')` because
`n_stations` piles up at 3). GAGES-II `MAJ_NDAMS_2009` is joined as
`regulation_stratum` and written on every row; it is **not** a third
random-split axis, because unmatched STAID cells would be an incomplete
factor. Dam labels were not invented from river names.

never_sealed networks do not appear as `split_role: sealed`.

## Honesty

- Exact max-overlap subset search; no 12-station truncation.
- Spatial filter omits over-wide groups; it does not drop the farthest
  station to salvage a cluster.
- Reviewer 161 equals naive zfill on this catalog; truncated combo does not.
- Catalog overlap is not concurrent daily completeness.
- DEFAULT_CATALOG remains `configs/network_catalog_v1.yaml`.
- This script does not rewrite `configs/design_freeze_v9.yaml` or
  `network_catalog_v1.yaml`. Split artifacts are separate files.
- design_freeze_v4 was not retargeted. Sealed temperatures were not opened.
