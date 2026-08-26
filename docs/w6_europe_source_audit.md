# W6 Europe source audit (2026-08-26)

## Decision

W6 adds **0 complete networks**. This is an honest source/QC result, not a
negative scientific result.

- UK EA remains 0 complete: River Derwent has two stations with daily values
  and one empty station.
- Hub'Eau remains 0 complete under provider QC. All 40 non-Loire 3+ station
  name clusters were preflighted (167/167 stations, zero request errors).
  Exactly 0/167 stations expose a Sandre qualification-1 (`Correcte`)
  observation. Code 4 is `Non qualifie` and is not accepted as approved data.
  Therefore no bulk download can produce a strict approved daily network, and
  no raw-span year is promoted to a daily year.
- Loire was not queried. Swiss temperature values were not queried or counted.

The executable audit is:

```bash
PYTHONPATH=src python scripts/71_w6_europe_source_audit.py --max-workers 4
```

It writes station attrition, network attrition, a FOEN API audit, and a combined
manifest under `results/framework/public_catalog/w6_*`.

## Why the old Hub'Eau products do not count

`hubeau_non_loire_chronicle_spans.csv` contains first/last timestamps from
instantaneous records. A timestamp span is not a daily-density result. The two
legacy `*_daily.csv` caches were produced before the year-window repair and do
not carry a strict provider-QC contract. They remain audit artifacts only.

The strict Hub'Eau downloader now:

1. requests only `code_qualification=1`;
2. refuses Loire/last-check station IDs;
3. partitions by calendar year, recursively splitting any response that would
   exceed Hub'Eau's 20,000-row page limit;
4. writes to a new `_daily_yearchunk_qc1.csv` cache suffix, so legacy caches
   cannot be silently reused;
5. labels the derived daily values as approved only after filtering.

The all-candidate preflight found no eligible observations, so step 3 was not
run in bulk. Downloading unqualified values merely to rediscover that they are
unqualified would add load without changing eligibility.

Sandre's qualification definition is documented at:
https://www.sandre.eaufrance.fr/definition/ALQ/2.2 . Qualification 1 is
`Correcte`; 2 is incorrect, 3 uncertain, and 4 unqualified.

## FOEN finding: no longer manual-only

The repository's old statement that historical FOEN daily water temperature
must always be ordered is obsolete as of this audit. FOEN now operates an
unauthenticated public GraphQL endpoint:

- endpoint: https://data.bafu.admin.ch/api
- documentation:
  https://api.data-platform.cloud.bafu.admin.ch/en/dataproduct-water-observations
- daily table: `data_1day_mean`
- parameter: `WT`
- release states: 1 provisional, 2 validated, 3 final/replaced

A metadata-only query returned 1,341 station rows. A timestamp-only probe of
station 2016 (Brugg) returned seven daily `WT` rows for 2025-01-01 through
2025-01-07, all release state 2. The GraphQL selection deliberately omitted
`value`, so no Swiss temperature outcome was opened.

FOEN's manual Hydrological Data Service still exists for legacy and special
orders:
https://www.bafu.admin.ch/en/hydrological-data-service-for-watercourses-and-lakes .
It is not required for the public daily GraphQL path.

## Direct next-source path

FOEN is technically the next executable source, but **not under the current
governance lock**: v9.1 still says Loire/Swiss cannot count toward T8 or the
non-North-America sealed quota. Do not run a Swiss value download or revise the
count merely because the API is now public. If the parent protocol explicitly
authorizes a prospective amendment, use this fixed ingestion contract before
opening values:

1. lock Swiss river-name/catchment clusters from station metadata and assign
   roles before value download;
2. query `data_1day_mean` in disjoint calendar-year windows with
   `parameterName=WT` and station number fixed;
3. retain release state 2 or 3; drop state 1;
4. require at least 300 distinct daily values per station-year;
5. require at least three stations sharing at least eight qualifying calendar
   years;
6. never use station `coverageFrom`/`coverageTo` as an eligibility substitute;
7. keep Swiss excluded from the present T8 count unless the protocol amendment
   is made before outcomes are opened.

Until that authorization exists, Swiss values stay closed. Hub'Eau Sandre
Correcte remains unusable: code 1 is absent on the audited long series, every
sampled point is code 4 Non qualifié, and bulk Correcte download was correctly
not started. Code 4 may be used later only as a separately labelled
unqualified source, never as T8 Correcte.

## UK EA spatial clustering (name clustering was insufficient)

River names are almost entirely blank (16/1964). Name clustering found only
River Derwent and did not add a T8 network. The next W6 Europe path clusters
the same catalog on lat/lon (complete-linkage, max pairwise geodesic cap).
A catalog 3+ cluster is not T8. `dateOpened` is not a daily-year span.

```bash
PYTHONPATH=src python scripts/89_uk_ea_spatial_daily.py
```

- 50 km is the declared cap (HUC8 50 km table exists as a diagnostic analog).
- 100 km is a sensitivity count, not the T8 count.
- T8 download roster is hydrometric IDs only (38 stations). Event-monitor
  clouds (1837 `E*` plus other logger codes) are catalog diagnostics, not T8.
- After daily download, overlap is scored first; groups whose overlap subset
  exceeds the cap are omitted, not shrunk.
- Hydrometric 50 km download (6 clusters, 26 stations requested, 13 with daily)
  still has `n_complete_enough: 0`. Best concurrent overlap is 5.91 years.
- complete_enough still requires 3 stations, ≥8 overlapping daily years, and
  ≥5×365 days with min 3 concurrent stations.
- Script 63 remains the metadata catalog; script 65 remains the Derwent name
  path. This script does not pad T8 with Derwent-only if spatial clusters fail.
