# NVE HydAPI panel — SECONDARY PROBE, not part of the sealed transport panel

`nve_hydapi` participated in v17 development, so `results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md` **Amendment 1** states:

> This amendment also records why `nve_hydapi` is **not** part of the sealed transport panel: that provider participated in v17 development, so new NVE basins are reported separately as a secondary probe, never as transport confirmation.

This directory is therefore a **secondary multi-agency probe feed**. Its networks must not enter `multi_agency_seal.json` and must not be pooled into the pre-declared transport verdict, whatever the per-station v17 status is. The panel is still useful as a same-agency, new-station replication of the frozen screen and as a boreal/alpine context description, and it is reported with that scope stated.

## What was ingested

| item | value |
|---|---|
| provider | `nve_hydapi` (NVE HydAPI, Norway) |
| parameter | `1003` — Vanntemperatur (water temperature) |
| resolution | `1440` min = provider **daily** statistic, aggregation method `Mean` |
| day definition | Norwegian normal time calendar day (fixed UTC+1), timestamped 11:00Z by NVE |
| quality kept | codes [2, 3] (PrimaryControlled / SecondaryControlled) and correction code 0 |
| assurance stratum | `quality_checked` (Amendment 2) |
| observed period covered by the panel | 1967-11-14 … 2025-08-12 |
| script | [`scripts/241_multi_agency_nve_ingest.py`](../../../../scripts/241_multi_agency_nve_ingest.py) |

## Headline counts

| quantity | value |
|---|---|
| parameter-1003 daily series rows in the HydAPI catalogue | 1216 |
| of those, river + measured + daily-mean rows | 929 |
| dropped: observation place not a river | 248 |
| dropped: daily archive is `Instantaneous`, not a mean | 39 |
| dropped: station id in the v17 roster | 57 |
| dropped: Svalbard (station-id basin 400) | 9 |
| **candidate basins (vassdrag) scanned** | **135** |
| **candidate stations** | **866** |
| raw observation rows returned | 3238298 |
| QC-passing station-days | 1454501 |
| stations with >= 1 complete calendar year | 223 |
| stations with >= 4 complete calendar years | 130 |
| **networks kept (>= 2 stations with >= 4 complete years)** | **21** |
| **stations in kept networks** | **93** |
| **complete station-years in kept networks** | **993** |
| kept networks in a basin the v17 roster never touched | 16 |
| kept networks sharing a basin with a v17 station | 5 |
| stations / complete station-years in v17-free networks | 47 / 532 |

## Networks

| network_id | basin name | stations | complete station-years | first date | last date | network is v17-free |
|---|---|---|---|---|---|---|
| `nve_basin_002` | Otta/Vorma-Lågen/Glommavassdraget | 30 | 331 | 1967-11-14 | 2024-08-11 | no (shares basin with a v17 station) |
| `nve_basin_012` | Drammensvassdraget | 11 | 139 | 1986-12-19 | 2023-11-08 | yes |
| `nve_basin_015` | Numedalslågen | 3 | 26 | 1984-09-06 | 2023-10-28 | yes |
| `nve_basin_021` | Otra | 4 | 50 | 1990-12-28 | 2024-12-03 | yes |
| `nve_basin_022` | Mandalselva | 3 | 35 | 1993-07-25 | 2023-09-04 | yes |
| `nve_basin_023` | Audna | 2 | 24 | 1993-05-03 | 2023-11-28 | yes |
| `nve_basin_062` | Vossovassdraget | 4 | 58 | 1987-06-04 | 2025-08-12 | yes |
| `nve_basin_072` | Aurlandsvassdraget | 2 | 36 | 1990-08-25 | 2022-10-25 | yes |
| `nve_basin_073` | Lærdalsvassdraget | 2 | 22 | 1972-12-01 | 2024-11-27 | yes |
| `nve_basin_075` | Fortunvassdraget | 2 | 18 | 2005-01-05 | 2023-03-20 | yes |
| `nve_basin_083` | Gaularvassdraget | 2 | 31 | 1990-08-16 | 2023-09-21 | yes |
| `nve_basin_087` | Breimsvassdraget | 2 | 27 | 1985-12-11 | 2023-11-08 | yes |
| `nve_basin_112` | Surna | 3 | 18 | 1996-03-25 | 2023-10-25 | no (shares basin with a v17 station) |
| `nve_basin_124` | Gråelva/Stjørdalsvassdraget | 4 | 32 | 1991-08-31 | 2023-06-11 | no (shares basin with a v17 station) |
| `nve_basin_139` | Sanddøla/Namsen | 2 | 14 | 1986-11-20 | 2023-06-18 | yes |
| `nve_basin_156` | Blakkåga/Raudvassåga/Langvassåga/Ranavassdraget | 2 | 18 | 1994-05-18 | 2023-06-07 | yes |
| `nve_basin_163` | Saltdalsvassdraget | 2 | 10 | 1979-06-16 | 2023-09-23 | yes |
| `nve_basin_166` | Laksåga | 2 | 12 | 1994-05-29 | 2023-10-05 | yes |
| `nve_basin_196` | Barduelva/Målselvvassdraget | 2 | 12 | 1993-10-20 | 2022-10-29 | yes |
| `nve_basin_212` | Tverrelva | 4 | 45 | 1993-10-20 | 2023-10-12 | no (shares basin with a v17 station) |
| `nve_basin_234` | Tana | 5 | 35 | 1994-06-17 | 2023-08-03 | no (shares basin with a v17 station) |

Stations with or without a v17-basin overlap: 16 networks contain no v17 station (16 of 21); the remaining 5 (`nve_basin_002`, `nve_basin_112`, `nve_basin_124`, `nve_basin_212`, `nve_basin_234`) sit in basins where v17 used at least one *other* station.

## Exact API filters

```
GET https://hydapi.nve.no/api/v1/Series?Parameter=1003
GET https://hydapi.nve.no/api/v1/Stations?StationId=<station_id>        # one call per station id
GET https://hydapi.nve.no/api/v1/Observations?StationId=<id[,id...]>&Parameter=1003&ResolutionTime=1440&ReferenceTime=<catalog_daily_start>/<catalog_daily_end>
Header: X-API-Key <public Sildre client key, discovered at runtime>
```

Batching: at most 8 station ids and about 20,000 estimated records per Observations request (HydAPI rejects more than 10 series per request). Raw JSON responses are cached verbatim under `raw_cache/`; the exact URL of every response is stored inside each cache file and in `ingest.json`.

## QC and drop accounting

Raw rows 3238298; dropped 1783797 (55.1%):

| drop reason | rows |
|---|---|
| `quality_not_primary_or_secondary_controlled` | 994787 |
| `value_missing_null` | 673663 |
| `correction_nonzero` | 114403 |
| `value_out_of_plausible_range` | 944 |

Reasons are assigned in a fixed precedence order, so they are disjoint and sum to the total. `value_missing_null` means NVE returned the day with a JSON-null value (its own missing-day marker); `quality_...` means the day was not primary/secondary controlled; `correction_nonzero` means ice correction, interpolation, a model value or a rejected-period value. Per-station counts are in `qc_ledger.csv`; the largest contributors are stations whose archive is mostly uncontrolled or interpolated.

## Caveats a reviewer would raise

- PROTOCOL SCOPE: MULTI_AGENCY_TRANSPORT_PROTOCOL.md Amendment 1 states that nve_hydapi 'is not part of the sealed transport panel' because the provider participated in v17 development, and that new NVE basins are 'reported separately as a secondary probe, never as transport confirmation'. This ingest is therefore a secondary-probe feed. Networks are flagged network_in_v17_basin when the station-id basin number already appears in the v17 station roster; use those flags to separate previously-touched basins from genuinely new ones.
- Assurance stratum (Amendment 2): every station is written with quality_assurance=quality_checked. NVE HydAPI quality codes 2 and 3 are PrimaryControlled / SecondaryControlled, i.e. checked at source; uncontrolled (1) and unknown (0) values were dropped, so no NVE series in this panel is provider_published_unqualified.
- Value resolution: HydAPI 1440-minute water temperature is returned as a float with ~6 decimals; NVE does not publish a rounding step, so the ingest neither rounds nor rescales. Accepted series are the provider's own daily statistic (aggregation method 'Mean' in the Observations response), not a re-aggregation of hourly or instantaneous data. Series whose 1440-minute archive reports method 'Instantaneous' were dropped.
- Day definition: HydAPI timestamps 1440-minute values at 11:00Z because the daily statistic is the calendar day in Norwegian normal time (UTC+1, fixed offset, no DST). The ingest snaps each value to that UTC+1 calendar day. A UTC-day interpretation would move 13 of 24 hours per value; the choice follows NVE's own documentation.
- Missing-day convention: missing daily values arrive as JSON null (about one third of all returned rows) and are dropped, as are quality/correction rejects; absent days stay blank in daily_wide_temperature.csv. Downstream readers must decide whether a blank is an outage or an unchecked day. qc_ledger.csv reports per-station drop counts and reasons, in a fixed precedence order.
- Regulation: Norwegian river temperature series are frequently downstream of hydropower regulation. catchmentRegTypeName and firstYearRegulation are carried in candidate_stations.csv and stations.csv so the transport analysis can stratify or report regulation status; the ingest does not exclude regulated basins.
- Basin grouping uses the station-id drainage-basin number (NVE vassdrag number, zero-padded), which matches the REGINE prefix of regineNo for every candidate station whose metadata still exists. NVE's current station registry returned HTTP 404 for many historical stations, so regineNo/riverName/hierarchy are missing for a large share of candidates (see ingest.json candidate_counts); the basin number from the station id is therefore used as the grouping key and network names fall back to the station river name. Networks are full vassdrag groupings, much larger than the 1-8 station subsets of the earlier p0_07 NVE probe.
- Svalbard stations (station-id basin 400, Ny-Alesund/Longyearbyen/Barentsburg/Pyramiden) were dropped as non-mainland; the panel is mainland Norway only.
- Dropped observation places: the parameter-1003 daily catalogue also contains Utslippspunkt (outfall), Innsjo (lake), Kum (manhole), Magasin (reservoir), Inntak (intake), Overlop (spillway), Grunnvannsror (groundwater), I ror (in pipe), Overforingstunnel (transfer tunnel), air temperature and snow-pillow series. None of them is river water temperature, so none is in this panel; see catalog_counts in ingest.json.
- No frozen-screen performance was computed on this panel: the ingest stops at QC and structural eligibility (>= 2 stations with >= 4 complete calendar years).
- 184 of 866 candidate stations carry a catchmentRegTypeName that indicates regulation (regulert); the share inside the kept networks is reported in stations.csv.
- 22 candidate stations sit in a coastal REGINE catchment (riverName/hierarchy contains KYSTFELT or FJORD). They are genuine river temperature series (observationPlace starts with 'Elv') and are kept, but a reviewer may want them flagged as fjord-influenced; the flag in_coastal_catchment is written per station.
- Metadata coverage: NVE's current station registry returned HTTP 404 for 488 of 866 candidate stations (mostly long-delisted series). Their `river_name`, `regineNo` and regulation flags are therefore blank; the station-id drainage-basin number is used for grouping, and the basin name is taken from whichever station in the basin still has metadata.
- Frozen-screen performance was **not** computed on this panel: the ingest stops at QC and structural eligibility. Any number here is coverage, not skill.

## Value sanity (not a performance check)

687160 written values, min -0.47 °C, max 24.17 °C, mean 5.59 °C; 15552 values below 0 °C (freshwater under-ice sensors read slightly negative), none below -0.5 °C, none above 30 °C.

## Files

| path | content |
|---|---|
| `networks/<network_id>/daily_wide_temperature.csv` | wide daily panel, `date` first, one column per station id, blank where missing |
| `networks/<network_id>/stations.csv` | the same station table restricted to one network |
| `stations.csv` | all panel stations with `quality_assurance`, complete-year list, dates, drop counts |
| `networks_manifest.csv` | per-network counts, date range, file paths and sha256 |
| `candidate_stations.csv` | every candidate station with catalog + station metadata and the v17-basin flag |
| `complete_station_years.csv` | one row per station-year |
| `qc_ledger.csv` | per-station QC drop counts by reason |
| `daily_long_qc.parquet` | QC-passing long table (station, date, value, provider flags) |
| `ingest.json` | retrieval UTC, API filters, counts, caveats, input hashes |
| `verification.json` | independent re-computation of every headline number |
| `raw_cache/` | verbatim HydAPI responses (catalogue, station metadata, observation batches) |

Independent verification: 103 checks, 0 failures (`PYTHONPATH=src python3 scratch/verify_nve_ingest.py`).

## Reproduction

```bash
PYTHONPATH=src python3 scripts/241_multi_agency_nve_ingest.py --stage all
PYTHONPATH=src python3 scratch/verify_nve_ingest.py
PYTHONPATH=src python3 scratch/make_nve_readme.py
```
