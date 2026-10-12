# Hub'Eau (France) river-temperature panel for the multi-agency transport test

Generated 2026-10-12T11:46:04Z by `scratch/hubeau_ingest/write_provider_readme.py` from the
emitted artifacts of `scripts/242_multi_agency_hubeau_ingest.py`.
Feeds `results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md`. No frozen-screen performance was computed on this panel.

## Panel

- networks: **14** (agency-native grouping: Hub'Eau river name,
  `libelle_cours_eau`, normalized; Loire and last-check ids excluded)
- stations: **47** (every station has >= 4 complete calendar years)
- complete station-years: **363**
- complete years per station: min 4, median 8, max 15
- retrieval: 2026-10-12T11:38:46Z; API requests logged: 2883; failures: 0

## Assurance level (read this before using the panel)

- **ALL stations are Sandre code 4 'Non qualifie' (unqualified) - this panel is a lower-assurance subset and must be reported as such**
- `quality_assurance` per station: {'provider_published_unqualified': 47}
- accepted Sandre codes: {4: 47}
- global Hub'Eau archive counts by code (API `count` field): code 1 = 5,499,909, code 2 = 0, code 3 = 0, code 4 = 47,898,863, all = 53,398,772
- audited pool: 80 stations on the capped
  candidate rivers; per-code totals there: {'1': 0, '2': 0, '3': 0, '4': 5587671}
- code-1 series do exist elsewhere in the archive (verified example station 10010140, code-1 data 2013-2023); none fall inside the audited candidate
  pool, so this panel stays in the unqualified stratum.
- protocol rule 3 (provider daily statistic): strict rule-3 non-conformance; ingest is honest and documented, admission is the coordinator's call

## Measurement provenance and aggregation rule

- source rows: Hub'Eau `temperature/chronique` instantaneous observations (`date_mesure_temp` + `heure_mesure_temp`)
- daily value: arithmetic mean of acceptable observations of the station's single accepted Sandre code within one calendar day
- minimum observations per day: **4**; days below the floor are dropped and counted, never interpolated
- days in span 226,725; days with observations 177,962; daily values formed 177,962; days with zero observations 48,763; days below the floor 0 (share of observed days 0.0000)
- observations downloaded 4,274,446; dropped by QC (unparsable date, non-finite or outside [-2.0, 45.0] degC) 340
- complete calendar year: every calendar day of a year that has ended carries a daily value (frozen rule: experiments/wrr_revision/universe.py full_calendar_year and scripts/234_wrr_sealed_confirmation_score.py _complete_years_from_series)
- sensitivity to the floor (raw_cache/complete_year_sensitivity.csv): floor 1 -> 387 station-years over 56 stations, floor 4 -> 387 station-years over 56 stations, floor 24 -> 291 station-years over 56 stations

## Resolved vs emitted (cap applied)

- catalogued stations 872; river stations kept 866 (dropped 6, 0.69%: Hub'Eau temperature stations carry DCE water-body metadata. Every station with a water-body code is a river water body (MasseDEauRiviere_VEDL2019); the catalog contains no lake/plan-d'eau, coastal, transitional or groundwater water-body class, so no station was dropped for those classes. Stations without a water-body code were kept only with explicit river-name evidence. Stations whose water-body label is itself a standing water body (lac/etang/retenue/reservoir/plan d'eau/graviere/lagune) were dropped, and sea/estuary stations were dropped only on station-name or water-body-class evidence -- a river reach label that merely names the sea or an estuary as its downstream boundary was retained.)
- stations with >= 4 years of observation span: 620
- candidate stations before the cap: 175 on 66 rivers
- cap: at most 15 networks and 4 stations per network; 51 rivers were beyond the network cap (`networks_beyond_cap.csv`, not downloaded) and 11 stations were beyond the per-network cap
- downloaded stations 56; emitted **14 networks / 47 stations / 363 station-years**; 1 network dropped after download for having fewer than 2 stations with >= 4 complete years (`networks_excluded_after_download.csv`)
- river-name ambiguity: 19 names mapped to more than one watercourse code, 46 stations excluded (`raw_cache/ambiguous_river_name_clusters.csv`)
- water-body notes: 14 kept stations have DCE reach labels that merely mention the sea or an estuary; 4 canalised-name stations kept and flagged

## Files

- `networks/<network_id>/daily_wide_temperature.csv` - wide daily panel, first column `date`,
  one column per station id, blank where a daily value was not formed
- `networks/<network_id>/stations.csv`, `networks/<network_id>/ingest.json`, `networks/<network_id>/README.md`
- `stations.csv` - all emitted stations with Sandre-code counts, QC day counts, complete
  years and quality labels
- `ingest.json` - retrieval UTC, exact API URL templates, counts by qualification code,
  aggregation rule, cap, assurance, prior-access check, caveats, failures
- `networks.csv`, `networks_beyond_cap.csv`, `networks_excluded_after_download.csv`, `stations_below_year_floor.csv`, `stations_dropped_waterbody_filter.csv`
- `raw_cache/` - every API response (gzip JSON envelope with url + retrieval time), `url_manifest.csv`, `station_table.csv`, `station_spans.csv`, `qualification_counts.csv`, `station_qc.csv`, `station_year_coverage.csv`, `complete_year_sensitivity.csv`, `network_inputs_manifest.csv` (network_id, input_path, sha256, station ids for the seal)

## Independent verification

`scratch/hubeau_ingest/verify_hubeau_ingest.py` recomputed complete years, daily values, station counts and quality labels from the raw cached payloads: 17 checks passed, 0 problems.

| network_id | river | stations | station-years | quality_assurance |
|---|---|---|---|---|
| hubeau_besbre | la Besbre | 3 | 32 | provider_published_unqualified |
| hubeau_cher | le Cher | 4 | 29 | provider_published_unqualified |
| hubeau_durance | La Durance | 3 | 15 | provider_published_unqualified |
| hubeau_garonne | La Garonne | 4 | 37 | provider_published_unqualified |
| hubeau_l_aisne | L'Aisne | 3 | 13 | provider_published_unqualified |
| hubeau_l_ariege | L'Ariège | 3 | 27 | provider_published_unqualified |
| hubeau_l_aveyron | L'Aveyron | 4 | 34 | provider_published_unqualified |
| hubeau_l_huisne | l'Huisne | 3 | 21 | provider_published_unqualified |
| hubeau_lot | Le Lot | 3 | 25 | provider_published_unqualified |
| hubeau_rhone | Le Rhône | 4 | 20 | provider_published_unqualified |
| hubeau_sarthe | la Sarthe | 4 | 39 | provider_published_unqualified |
| hubeau_seine | La Seine | 2 | 9 | provider_published_unqualified |
| hubeau_sioule | la Sioule | 4 | 32 | provider_published_unqualified |
| hubeau_tarn | Le Tarn | 3 | 30 | provider_published_unqualified |

