# Catalog v3 HUC8 feasibility (competing / adversarial)

Metadata only. Daily temperature values were **not** downloaded.
Sealed temperatures were **not** opened. `network_catalog_v1.yaml` was
**not** remapped. This is a grouping-rule correction (HUC8 subbasin vs
name×HUC2 region), not a relaxation, and not T2.

## Exact counts (this implementation)

- HUC8, 3 stations, 8-year **exact** subset: **166**
- HUC8, 3 stations, 8-year **truncated combo (n>12 → 12)**: **166**
- HUC8, 3 stations, 8-year **naive zfill(8)[:8]**: **161**
- Reviewer's published figure: **161**. Reproduced **exactly** by naive `str(huc).zfill(8)[:8]`, not by truncated combo search.
- Exact vs 161: delta **5** (official HUC prefix restores five groups naive zfill splits or drops).
- Exact vs truncated-combo network count: delta **0**.
- Groups with n_stations_available > 12: **9**. Truncation still finds a ≥3-station subset among the 12 longest, so the *count* does not move; `n_stations` is capped at 12 and undercounts those groups (n_stations differs in **8** networks).
- Production v2 `huc8_only` 3st/8y (already on disk): **166**.

161 is **not** an exact search. Do not copy 161 into a T2 numerator.

## Contrast table

| Rule | 3st/8y | 4st/8y |
| --- | ---: | ---: |
| name×official HUC2 | 98 | 44 |
| official HUC4-only | 126 | 101 |
| official HUC6-only | 145 | 110 |
| official HUC8-only exact | 166 | 105 |
| HUC8 max_pair ≤ 100 km (filter) | 150 | 95 |
| HUC8 max_pair ≤ 50 km (filter) | 92 | 51 |
| v1 name×raw HUC prefix whole-group | 31 | 31 |

## Missouri River (attack 3)

missouri_river_huc10 lists 18 stations under HUC2 10; official HUC8 splits them into 12 subbasins: 10030101, 10030102, 10040104, 10060001, 10230001, 10230006, 10240001, 10240005, 10240011, 10300101, 10300102, 10300200.
HUC8 ids: 10030101, 10030102, 10040104, 10060001, 10230001, 10230006, 10240001, 10240005, 10240011, 10300101, 10300102, 10300200.
It must **not** survive as one HUC8 network.

## Catalog overlap is not qualified years (attack 7)

`daily_begin` / `daily_end` are first and last catalog dates. They are
not concurrent daily completeness, not QC, and not 2000–2024 coverage.
The 12 downloaded rivers already collapsed 12→6 under a same-day rule.
Expected post-download attrition 25–40%. Even 161×0.65≈105 only clears
the n_networks_min=100 CI floor as a **hope**, not a result. 150 still
needs Europe and/or a documented 3st/6y failure-closure. **T2 is not
done at 161.**

## Distance (attack 4–5)

Pairwise cap is haversine km, Earth radius 6371 km. A 50 km cap expressed
in degrees is meaningless near Alaska vs Florida. Missing lat/lon:
never_zero_or_inf: NaN if fewer than two located stations; distance cap drops unlocated stations then re-validates overlap; does not treat missing coordinates as 0 km or infinite km.
Default distance_mode is **filter** (omit groups that exceed the cap) not
silent shrink of the max-overlap subset.

## NLDI (attack 6)

HUC8 does not guarantee flow connectivity. Groups with
`flow_connected=false|partial` are retained as
`spatially_proximate_not_flow_connected`. Live NLDI of all groups is
Implementer A's job; this competing run fixture-tests the parser and
optionally queries 2–3 groups. 404 = isolated origin, not a delete.
429 is retried; leftover failures are `not_queried`, not faked.

## Split (attack 8–9)

Stratified 50/20/30 by climate_band × size tertile. Assignment key is
SHA-256(`seed\\tnetwork_id`) with seed **20260826**, locked **before**
any new download. never_sealed (12 burned rivers + jinsha +
chattahoochee, matched by site overlap / name tokens) cannot be sealed.
Loire and Swiss Aare-Rhine have no public dated daily values here and
**cannot** fill the 10 non-North-America sealed floor. USGS-only sealed
will not meet sealed≥40 or 10 non-NA; that shortfall is recorded, not
papered over. regulation_stratum = `unknown_until_gages` (the 335-row
regulation-panel extract is not catalog-wide GAGES-II).

## What this is not

- Not a recovery score.
- Not T2.
- Not a rewrite of network_catalog_v1.
- Not a temperature download.
