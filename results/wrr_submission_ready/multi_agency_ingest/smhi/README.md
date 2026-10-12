# SMHI multi-agency ingest (provider: smhi, parameter 4 "Vattendragstemperatur")

Written 2026-10-12T10:03:43Z by `scripts/240_multi_agency_smhi_ingest.py`
(`PYTHONPATH=src python3 scripts/240_multi_agency_smhi_ingest.py --qc-stratum provider_published_unqualified`).

## What was downloaded

- Catalogue: `https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/4.json` — 176 stations, unit '°C'.
- Series: `https://opendata-download-hydroobs.smhi.se/api/version/latest/parameter/4/station/{station_id}/period/corrected-archive/data.csv` (`corrected-archive`, the only period served for parameter 4).
- 176 of 176 stations downloaded, 0 failures;
  1063746 parsed rows over 1063746 quality-code-`O` rows.
- Raw bytes are cached in `raw_cache/` (gitignored) with sha256 per file in
  `raw_cache_manifest.csv`; `stations_all.csv` carries per-station QC for all 176 stations.
- Coverage: 1946-04-01 .. 2003-05-05; median station span
  1976-09 .. 1990-10 (87 stations end before
  1990, 26 reach 2000). Every station is
  catalogued `measuringStations = ADDITIONAL` ("Övriga stationer" = outside SMHI's own network)
  and `active = false`, and every series row carries quality code `O`.

## QC legend (verbatim, extracted from the series files)

- Grön (G) = Kontrollerade och godkända värden.
- Gul (Y) = Grovt kontrollerade värden.
- Orange (O) = Okontrollerade värden.

Full copy: `QC_legend_verbatim.json`, `station_header_block.txt`, and `ingest.json`.

## Why the uncontrolled code was accepted

`MULTI_AGENCY_TRANSPORT_PROTOCOL.md` **Amendment 2 (assurance strata)** defines
`quality_checked` (provider documents checked/coarsely-checked values) and
`provider_published_unqualified` (provider publishes the series but labels it
uncontrolled/unqualified — SMHI `O`, Hub'Eau Sandre code 4). Under the strict
`quality_checked` gate this provider yields nothing: 0 of 1063746 rows carry
`G` or `Y`, so 0 stations and 0 networks — recorded in
`QC_AND_ELIGIBILITY_FAILURE.md`, retained unchanged as the strict-gate audit.

This run therefore uses `--qc-stratum provider_published_unqualified`. The admitted panel is:

| item | value |
|---|---|
| stratum | `provider_published_unqualified` |
| accepted quality codes | `O` |
| stations with >= 4 complete calendar years | 118 |
| networks (>= 2 such stations per `catchmentNumber`) | 16 |
| complete station-years of those stations | 1549 |
| ... of which inside emitted networks | 1372 |
| ... of which stranded in catchments with < 2 eligible stations | 177 |
| stations appearing in emitted panels (columns) | 143 |
| eligible (>= 4-year) stations inside emitted panels | 101 |
| complete station-years summed over all 176 downloaded stations | 1601 |

The pre-decision strict-gate diagnostic predicted exactly the network and station counts
above (118 stations with >= 4 complete years, 16 networks; see
`scratch/smhi_verify_counterfactual_station_years.csv` and
`scratch/smhi_verify_counterfactual_networks.csv`), so the decision admitted the panel
that was on the table with no extra filtering. That diagnostic's headline
"1,601 complete station-years" is the **all-station** sum; it includes
52 years contributed by the
58 stations below the 4-year bar, which is why the
eligible-station total here is 1549.

Values are labelled uncontrolled **by the provider**; no re-checking was performed here.
The stratum travels into the seal as the per-station `quality_assurance` column of
`stations.csv`, and the pooled transport verdict must be reported with the per-stratum
breakdown and the sensitivity that excludes this stratum (Amendment 2, rules 2-3).

## Caveats a reviewer must carry

1. **Day boundary / timezone.** The date column header is `Datum (svensk sommartid)`
   (Swedish summer time, UTC+2). The SMHI download-portal text separately says file times
   are UTC (+1 h normal, +2 h summer). The statements conflict; date-only panels are
   unaffected on the same calendar date, but any UTC/diurnal alignment would be wrong.
2. **Statistic.** SMHI documents parameter 4 as
   "Daglig uppgift om vattendragstemperaturer i vattendrag i Sverige." with "Enhet: Grader Celsius". The daily aggregation
   operator (mean vs. instantaneous reading) is not documented, so `measurement_statistic`
   records a daily provider statistic in °C, not a confirmed daily mean.
3. **Not SMHI's own network.** Every station is `Övriga stationer` (third-party data
   collected and stored by SMHI), so this is not SMHI's official station network.
4. **Historical.** The archive ends in 2003 and no parameter-4 station is active; the panel
   does not overlap the recent-period regime of the frozen model's development panel.
5. **No scoring here.** Ingest and QC only; no frozen-screen performance was computed on
   this data by this script.
6. **Some stations are short.** Rows per station run 6 to
   16721 (median 4361); complete-year counting decides who
   enters a network.

## Artifacts

`networks/<network_id>/daily_wide_temperature.csv` (first column `date`, one column per
station id, one row per calendar day from min to max date, blank where missing),
`networks/<network_id>/stations.csv`, `stations.csv`, `stations_all.csv`,
`station_catalog.csv`, `station_years.csv`, `networks_summary.csv`,
`networks_not_eligible.csv`, `hydropower_evidence.csv`, `INGEST_STATUS.json`,
`QC_AND_ELIGIBILITY_FAILURE.md` (strict-gate record), `QC_legend_verbatim.json`,
`ingest.json`, `run.log`, `raw_cache_manifest.csv`, `raw_cache/`.

Textual only: 117 of 176
station names contain "KRV" (kraftverk) and
48 contain "FORS"/"FORSEN";
see `hydropower_evidence.csv`. This is name evidence, not a regulation classification.

Latitudes 55.45-68.36 N
(109 of 176 north of 60 N), consistent with the
`boreal_nordic` context used for this provider in `scripts/249`.
